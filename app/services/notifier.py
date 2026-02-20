import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pprint import pprint

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from app.keyboards.markups import create_kb, keyboard_namaz
from app.services import db
from app.services.namaz_api import get_namaz, NAMAZ
from config import BOT_TOKEN

logger = logging.getLogger(__name__)

# Соответствие английских названий молитв русским (для уведомлений)
PRAYER_NAMES = {
    'time_fajr': ('Фаджр', 'alarm_fajr', 'push_fajr'),
    'time_sunrise': ('Шурук', 'alarm_sunrise', 'push_sunrise'),
    'time_dhuhr': ('Зухр', 'alarm_dhuhr', 'push_dhuhr'),
    'time_asr': ('Аср', 'alarm_asr', 'push_asr'),
    'time_maghrib': ('Магриб', 'alarm_maghrib', 'push_maghrib'),
    'time_isha': ('Иша', 'alarm_isha', 'push_isha')
}
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))

async def check_notifications(bot: Bot):
    """
    Проверяет каждую минуту:
    - Если до молитвы осталось меньше 20 минут, а уведомление ещё не отправлено (alarm=False) → отправляет "Скоро намаз".
    - Если после молитвы прошло больше 10 минут, а уведомление ещё не отправлено (push=False) → отправляет "Намаз прошёл".
    После отправки соответствующий флаг устанавливается в True.
    """
    now = datetime.now(timezone.utc)
    users = await db.get_all_users()
    for user in users:
        print(user.user_id)
        print(user.city_name)
        updated = False
        for field, (name_ru, alarm_field, push_field) in PRAYER_NAMES.items():
            prayer_time = getattr(user, field, None)
            if prayer_time is None:
                continue
            print(field)
            print(prayer_time)
            # Разница в минутах (положительная, если молитва в будущем)
            if prayer_time.tzinfo is None:
                prayer_time = prayer_time.replace(tzinfo=timezone.utc)
            diff_minutes = (prayer_time - now).total_seconds() / 60.0
            print(diff_minutes)

            # 1. Уведомление за 20 минут до намаза (если ещё не отправляли)
            if 0 < diff_minutes <= 20 and not getattr(user, alarm_field):
                try:
                    await bot.send_message(
                        user.user_id,
                        f"⚠️ До намаза {name_ru} осталось менее 20 минут!"
                    )
                    setattr(user, alarm_field, True)
                    updated = True
                    logger.info(f"Уведомление о скором намазе {name_ru} отправлено пользователю {user.user_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю {user.user_id}: {e}")

            # 2. Уведомление через 10 минут после намаза (если ещё не отправляли)
            elif diff_minutes < -10 and not getattr(user, push_field):
                try:
                    await bot.send_message(
                        user.user_id,
                        f"✅ Вы совершили {name_ru}?",
                        reply_markup=keyboard_namaz(field.replace('time_', ''))
                    )
                    setattr(user, push_field, True)
                    updated = True
                    logger.info(f"Уведомление о прошедшем намазе {name_ru} отправлено пользователю {user.user_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю {user.user_id}: {e}")

        if updated:
            # Сохраняем изменения в БД
            async with db.Session() as session:
                session.add(user)
                await session.commit()


async def hourly_date_check():
    logger.info("Starting hourly date check")
    users = await db.get_all_users()
    if not users:
        logger.info("No users found")
        return

    now_utc = datetime.now(timezone.utc)
    updated_count = 0

    for user in users:
        logger.info(user.user_id)
        try:
            # Compute local date
            local_datetime = now_utc + timedelta(hours=user.timezone)
            local_date = local_datetime.date()
            logger.info(local_datetime)
            logger.info(user.date_now)
            # If date hasn't changed, skip
            if user.date_now == local_date:
                continue

            logger.info(f"User {user.user_id}: date changed from {user.date_now} to {local_date}")

            # Fetch new timings
            date_str = local_datetime.strftime('%d-%m-%Y')
            timings = None
            for attempt in range(3):  # retry up to 3 times
                timings = await get_namaz(date_str, user.latitude, user.longitude)
                if timings:
                    break
                await asyncio.sleep(0.5)

            if not timings:
                logger.error(f"Failed to fetch namaz times for user {user.user_id} after retries")
                continue

            # Prepare updates
            prayer_updates = {}
            for prayer in NAMAZ:
                prayer_time_str = timings.get(prayer)
                if not prayer_time_str:
                    continue

                # Local prayer datetime (naive)
                local_prayer = datetime.strptime(f"{date_str} {prayer_time_str}", "%d-%m-%Y %H:%M")

                # Convert to UTC naive and then aware
                prayer_utc_naive = local_prayer - timedelta(hours=user.timezone)
                prayer_utc = prayer_utc_naive.replace(tzinfo=timezone.utc)

                # Store in corresponding time_* field
                prayer_updates[f"time_{prayer.lower()}"] = prayer_utc

            # Reset all alarm and push flags
            alarm_push_fields = [
                'alarm_fajr', 'push_fajr',
                'alarm_sunrise', 'push_sunrise',
                'alarm_dhuhr', 'push_dhuhr',
                'alarm_asr', 'push_asr',
                'alarm_maghrib', 'push_maghrib',
                'alarm_isha', 'push_isha'
            ]
            for field in alarm_push_fields:
                prayer_updates[field] = False

            # Update date_now
            prayer_updates['date_now'] = local_date

            # Apply updates to database
            await db.update_user_prayers(user.user_id, prayer_updates)
            updated_count += 1
            logger.info(f"Updated prayer times for user {user.user_id}")
            await bot.send_message(user.user_id, f'Произошла смена даты - {date_str}')

        except Exception as e:
            logger.exception(f"Error processing user {user.user_id}: {e}")

    logger.info(f"Hourly date check completed. Updated {updated_count} users.")