import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from config import config
from signals.generator import expire_old_signals, generate_signal
from signals.formatter import format_signal_card
from bot.handlers import build_signal_keyboard
from bot.notifications import send_message
from trading.position_tracker import check_positions
from database import repository
from database.models import SignalStatus


async def analyze_market() -> None:
    """Анализ рынка по всем символам — запускается каждые 15 минут."""
    logger.info("Запуск анализа рынка...")

    # Сначала сбрасываем просроченные сигналы
    expire_old_signals()

    # Анализируем каждый символ
    for symbol in config.TRADING_SYMBOLS:
        signal = generate_signal(symbol)
        if signal is None:
            continue

        # Отправляем карточку с кнопками в Telegram
        text = format_signal_card(signal)
        keyboard = build_signal_keyboard(signal.id)

        from telegram import Bot
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        msg = await bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        # Сохраняем message_id чтобы потом обновлять карточку
        repository.update_signal_status(signal.id, SignalStatus.PENDING, telegram_message_id=msg.message_id)
        logger.info(f"Сигнал #{signal.id} отправлен в Telegram")


async def monitor_positions() -> None:
    """Проверка открытых позиций — запускается каждые 2 минуты."""
    await check_positions()


async def weekly_report() -> None:
    """Еженедельный отчёт — каждое воскресенье в 20:00."""
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from database.models import Trade
    from database.repository import engine
    from signals.formatter import format_weekly_report

    week_ago = datetime.utcnow() - timedelta(days=7)
    with Session(engine) as session:
        week_trades = list(session.scalars(
            select(Trade).where(Trade.created_at >= week_ago)
        ).all())

    stats = repository.get_statistics()
    text = format_weekly_report(stats, week_trades)
    await send_message(text)
    logger.info("Еженедельный отчёт отправлен")


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Анализ рынка каждые 15 минут
    scheduler.add_job(analyze_market, "interval", minutes=15, id="analyze_market")

    # Мониторинг позиций каждые 2 минуты
    scheduler.add_job(monitor_positions, "interval", minutes=2, id="monitor_positions")

    # Еженедельный отчёт — воскресенье 20:00 UTC
    scheduler.add_job(weekly_report, "cron", day_of_week="sun", hour=20, minute=0, id="weekly_report")

    return scheduler
