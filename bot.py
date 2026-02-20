import asyncio
from logger import logger

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.handlers.common import common_router
from app.handlers.location import location_router
from app.services.db import init_db
from app.services.notifier import check_notifications, hourly_date_check
from config import BOT_TOKEN, ADMIN_ID



async def set_commands(bot: Bot):
    commands = [
        BotCommand(command='/start', description='Запустить бота')
    ]
    await bot.set_my_commands(commands)


async def bot_started(bot: Bot):
    await bot.send_message(chat_id=ADMIN_ID, text='Бот Запущен')


async def main():
    logger.info('Starting bot')

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher(storage=MemoryStorage())


    # Подключаем роутеры
    dp.include_router(common_router)
    dp.include_router(location_router)

    await set_commands(bot)
    await bot_started(bot)
    await init_db()

    # Запуск планировщика
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_notifications,
        trigger=IntervalTrigger(seconds=20),
        kwargs={'bot': bot},
        id='prayer_notifier'
    )
    scheduler.add_job(
        hourly_date_check,
        trigger=IntervalTrigger(minutes=1),
        id='hourly_date_check'
    )
    logger.info("Hourly date check scheduler added")
    scheduler.start()
    logger.info("Планировщик уведомлений запущен")

    # Удаляем вебхук и пропускаем накопившиеся обновления
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
