import asyncio
import sys

from loguru import logger

from config import config
from database.repository import init_db
from bot.telegram_bot import build_application
from scheduler.jobs import build_scheduler


def setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
        level="INFO",
        colorize=True,
    )
    logger.add(
        "logs/traider.log",
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
        encoding="utf-8",
    )


async def main() -> None:
    setup_logging()
    logger.info("Запуск TRAIDER...")

    # Проверяем конфиг
    try:
        config.validate()
    except ValueError as e:
        logger.error(str(e))
        logger.error("Создайте файл .env на основе .env.example и заполните все значения")
        sys.exit(1)

    # Инициализируем БД
    logger.info("Инициализация базы данных...")
    init_db()

    # Запускаем планировщик задач
    logger.info("Запуск планировщика...")
    scheduler = build_scheduler()
    scheduler.start()

    # Запускаем Telegram-бот
    logger.info("Запуск Telegram-бота...")
    app = build_application()
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    logger.info("✅ TRAIDER запущен и анализирует рынок каждые 15 минут")
    logger.info(f"Символы: {', '.join(config.TRADING_SYMBOLS)}")
    logger.info(f"Режим: {'TESTNET' if config.BINANCE_TESTNET else 'PRODUCTION'}")

    # Держим процесс живым
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка TRAIDER...")
    finally:
        scheduler.shutdown()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("TRAIDER остановлен")


if __name__ == "__main__":
    asyncio.run(main())
