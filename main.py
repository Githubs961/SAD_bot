import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from config import load_config
from database import init_db, expire_old_payments
from handlers import user, payments ,other
from handlers.payments import payments_router, auto_check_payments
from keyboard.keyboard import set_main_menu

# Инициализируем логгер
logger = logging.getLogger(__name__)

async def main():
    # Конфигурируем логирование
    logging.basicConfig(
        level=logging.INFO,
        format='%(filename)s:%(lineno)d #%(levelname)-8s '
               '[%(asctime)s] - %(name)s - %(message)s')
    # Вывод в консоль о начале запуска бота
    logger.info('Start_bot')

    # Загрузка переменных из пакета config_data
    config = load_config('.env')

    # Создаем объекты бота и диспетера
    bot = Bot(config.tg_bot.token, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher()
    # # Добавление меню в бота
    await set_main_menu(bot)
    #
    # # Регистриуем роутеры в диспетчере
    dp.include_router(user.router)
    dp.include_router(payments.payments_router)

    # 🔥Автопроверка платежа
    asyncio.create_task(auto_check_payments(bot))
    # Удаление из БД старых платежей(PENDING)
    asyncio.create_task(expire_old_payments())

    # Пропускаем накопившиеся апдейты и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)



if __name__ == '__main__':
    init_db()   # создаём таблицы при первом запуске
    asyncio.run(main())