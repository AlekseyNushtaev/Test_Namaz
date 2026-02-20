import asyncio
import datetime
from pprint import pprint

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

from .common import cmd_start_help
from ..keyboards.markups import city_confirm_dialog, get_main_markup
from ..services import db, msg_templates
from ..services.map_api import get_loc_geocode, get_loc_timezone
from ..services.namaz_api import NAMAZ, get_namaz

location_router = Router()
MAIN_MARKUP = get_main_markup()


class SetLocation(StatesGroup):
    waiting_loc_name = State()
    confirm_loc_name = State()


@location_router.message(F.text.startswith('🌍'))
async def location_start(message: Message, state: FSMContext):
    await message.answer(text='Введите название населенного пункта для поиска', reply_markup=ReplyKeyboardRemove())
    await state.set_state(SetLocation.waiting_loc_name)


@location_router.message(StateFilter(SetLocation.waiting_loc_name))
async def location_search(message: Message, state: FSMContext):
    response = await get_loc_geocode(message.text)
    if response['status'] == 'Error':
        for i in range(3):
            response = await get_loc_geocode(message.text)
            await asyncio.sleep(0.3)
            if response['status'] != 'Error':
                break
    if response['status'] is None:
        msg = 'Ничего не найдено. Проверьте правильность написания пункта, или попробуйте ' \
              'ввести ближайший крупный населенный пункт'
        await message.answer(msg)
        return
    elif response['status'] == 'Multiple':
        msg = 'Найдено несколько вариантов, уточните положение, ' \
              'например указав область или страну'
        await message.answer(msg)
        return
    elif response['status'] == 'Error':
        msg = 'Ошибка во время поиска местности, попробуйте еще раз.\n ' \
              'Спасибо'
        await message.answer(msg)
        return

    markup = city_confirm_dialog()
    await state.update_data(response)
    await message.answer(response['display_name'], reply_markup=markup)
    await state.set_state(SetLocation.confirm_loc_name)


@location_router.callback_query(F.data.in_(['yes_city', 'no_city']), StateFilter(SetLocation.confirm_loc_name))
async def location_confirm(call: CallbackQuery, state: FSMContext):
    if call.data == 'no_city':
        msg = 'Попробуем еще раз.\nВведите название населенного пункта для поиска'
        await call.message.edit_text(msg)
        await state.set_state(SetLocation.waiting_loc_name)
    elif call.data == 'yes_city':
        location = await state.get_data()
        lat = float(location['lat'])
        lon = float(location['lon'])
        timezone = await get_loc_timezone(lat, lon)
        if timezone is False:
            await call.message.edit_text('Не удалось определить часовой пояс. Попробуйте позже.')
            await state.clear()
            return
        # Сохраняем город непосредственно в запись пользователя
        await db.set_user_city(
            user_id=call.from_user.id,
            city_name=location['display_name'],
            lat=lat,
            lon=lon,
            tz=timezone
        )
        time_now_utc = datetime.datetime.now(datetime.timezone.utc)
        # Локальная дата для запроса к API (сегодня по местному времени)
        local_datetime = time_now_utc + datetime.timedelta(hours=timezone)
        date = local_datetime.strftime('%d-%m-%Y')

        # Получаем расписание на сегодня
        for i in range(3):
            timings = await get_namaz(date, lat, lon)
            if timings:
                break
            await asyncio.sleep(0.5)

        if not timings:
            # В случае ошибки API просто выходим, ничего не обновляем
            return

        # Для каждой молитвы вычисляем UTC-время и решаем, что записать в БД
        prayer_updates = {}
        for prayer in NAMAZ:  # NAMAZ импортирован из namaz_api
            prayer_time_str = timings.get(prayer)
            if not prayer_time_str:
                continue

            # Локальное время молитвы (naive)
            local_prayer = datetime.datetime.strptime(f"{date} {prayer_time_str}", "%d-%m-%Y %H:%M")

            # Переводим в UTC (naive) и делаем aware
            prayer_utc_naive = local_prayer - datetime.timedelta(hours=timezone)
            prayer_utc = prayer_utc_naive.replace(tzinfo=datetime.timezone.utc)
            if time_now_utc > prayer_utc:
                prayer_updates[f"time_{prayer.lower()}"] = None
            else:
                prayer_updates[f"time_{prayer.lower()}"] = prayer_utc
            prayer_updates['date_now'] = local_datetime.date()
        if prayer_updates:
            await db.update_user_prayers(call.from_user.id, prayer_updates)

        msg = f'{call.from_user.username}, ваше местоположение установлено как ' \
              f'{location["display_name"].split(",")[0]}'
        await call.message.edit_text(msg)
        msg = msg_templates.get_text_main(call.from_user.username, location['display_name'].split(',')[0])
        await call.message.answer(text=msg, reply_markup=MAIN_MARKUP)
    await call.answer()
