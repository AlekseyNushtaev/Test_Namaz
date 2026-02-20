import asyncio
import datetime
import random
import urllib.parse
from datetime import timedelta
from pprint import pprint

from aiogram import Router, F, Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, KeyboardButtonRequestUsers, KeyboardButton, ReplyKeyboardMarkup, \
    UsersShared, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN
from logger import logger
from ..services import db
from ..services import msg_templates
from ..keyboards.markups import get_main_markup
from ..services.models import Session, User
from ..services.namaz_api import get_namaz, get_next, NAMAZ

common_router = Router()
MAIN_MARKUP = get_main_markup()
request_storage = {}
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))


@common_router.message(Command('start', 'help'))
@common_router.message(F.text.startswith('⁉'))
async def cmd_start_help(message: Message, state: FSMContext):
    await state.clear()
    city = await db.get_user_city(message.from_user.id)

    if not city:
        logger.info('Юзера нет записываем в БД')
        city = await db.add_user(message.from_user.id)
        time_now_utc = datetime.datetime.now(datetime.timezone.utc)

        # Локальная дата для запроса к API (сегодня по местному времени)
        local_datetime = time_now_utc + timedelta(hours=city[3])
        date = local_datetime.strftime('%d-%m-%Y')

        # Получаем расписание на сегодня
        for i in range(3):
            timings = await get_namaz(date, city[1], city[2])
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
            prayer_utc_naive = local_prayer - timedelta(hours=city[3])
            prayer_utc = prayer_utc_naive.replace(tzinfo=datetime.timezone.utc)
            if time_now_utc > prayer_utc:
                prayer_updates[f"time_{prayer.lower()}"] = None
            else:
                prayer_updates[f"time_{prayer.lower()}"] = prayer_utc
            prayer_updates['date_now'] = local_datetime.date()
        if prayer_updates:
            await db.update_user_prayers(message.from_user.id, prayer_updates)
    msg = msg_templates.get_text_main(message.chat.username, city[0].split(',')[0])
    await message.answer(text=msg, reply_markup=MAIN_MARKUP)


@common_router.message(F.text.startswith(('🕌', '🕋')))
async def day_handler(message: Message):
    city = await db.get_user_city(message.from_user.id)
    timestamp = message.date + timedelta(hours=city[3])
    if message.text.startswith('🕋'):
        timestamp += timedelta(days=1)
    date = timestamp.strftime('%d-%m-%Y')
    timings = await get_namaz(date, city[1], city[2])
    if timings is None:
        msg = 'Ошибка загрузки данных, попробуйте еще раз.\nСпасибо.'
    else:
        msg = msg_templates.get_text_day(city[0].split(',')[0], date, timings)
    await message.answer(text=msg, reply_markup=MAIN_MARKUP)


@common_router.message(F.text.startswith('⏰'))
async def next_handler(message: Message):
    city = await db.get_user_city(message.from_user.id)
    timestamp = message.date + timedelta(hours=city[3])
    namaz = await get_next(timestamp, city[1], city[2])
    msg = msg_templates.get_text_next(city[0].split(",")[0], namaz)
    await message.answer(text=msg, reply_markup=MAIN_MARKUP)


@common_router.callback_query(F.data.startswith('yesna'))
async def namaz_yes(callback: CallbackQuery):
    # Извлекаем название намаза из callback_data (например, "yes_fajr" -> "fajr")
    name_namaz = callback.data.replace('yesna_', '').lower()
    await callback.answer()

    # Получаем объект пользователя из БД
    async with Session() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        user = result.scalar_one_or_none()

    if not user:
        await callback.message.answer("Пользователь не найден. Попробуйте /start")
        return

    # Русские названия намазов в порядке, соответствующем NAMAZ
    prayer_names_ru = {
        'fajr': 'ФАДЖР',
        'sunrise': 'ШУРУК',
        'dhuhr': 'ЗУХР',
        'asr': 'АСР',
        'maghrib': 'МАГРИБ',
        'isha': 'ИША'
    }

    # Определяем порядок намазов (индексы)
    order = [p.lower() for p in NAMAZ]  # ['fajr', 'sunrise', 'dhuhr', 'asr', 'maghrib', 'isha']
    try:
        selected_index = order.index(name_namaz)
    except ValueError:
        await callback.message.answer("Неизвестный намаз")
        return

    # Формируем строки для каждого намаза
    lines = []
    for idx, prayer in enumerate(order):
        # Получаем время из модели (поле time_<prayer>)
        time_attr = getattr(user, f"time_{prayer}", None)
        if time_attr is None:
            time_str = "--:--"
        else:
            # Конвертируем UTC в локальное время пользователя
            local_time = time_attr + timedelta(hours=user.timezone)
            time_str = local_time.strftime("%H:%M")

        # Определяем статус
        if idx <= selected_index:
            status = "✅"
        else:
            status = "предстоит, по милости Аллаха"

        lines.append(f"{prayer_names_ru[prayer]} - {time_str}   {status}")

    # Заголовок
    username = callback.from_user.username
    date_header = f"Дата - {user.date_now.strftime('%d-%m-%Y')}\n"
    header = f"Совершенные намазы {f'@{username}' if username else ''}:\n" if username else "Совершенные намазы:\n\n"

    # Текст сообщения
    msg_text = "\n\n" + date_header + header + "\n".join(lines) + "\n\n"
    # msg_text += '<a href="https://t.me/Test3136_bot">Надежный помощник в соблюдении совершения намаза</a>\n'
    msg_text += '«Тот, кто указал на благое, получает такую же награду, как и совершивший его». (Сахих Муслим)'

    # Генерируем уникальный request_id
    request_id = random.randint(1, 2_000_000_000)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Поделиться с Уммой",
                url=f"https://t.me/share/url?url=https://t.me/Test3136_bot?start=ref{callback.from_user.id}&text={urllib.parse.quote(msg_text)}"
            )
        ]
    ])

    # Отправляем сообщение с этой клавиатурой
    sent_msg = await callback.message.answer(msg_text, reply_markup=keyboard, parse_mode='HTML')


