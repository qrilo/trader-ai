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


_scheduler: AsyncIOScheduler = None


def get_scheduler() -> AsyncIOScheduler:
    return _scheduler


async def analyze_market() -> None:
    """Анализ рынка — у каждого пользователя свой таймфрейм (троттлинг по last_market_analysis_at)."""
    from datetime import datetime

    users = repository.get_active_users()

    if not users:
        logger.warning("Нет активных пользователей с настроенными API ключами")
        return

    now = datetime.utcnow()
    logger.debug(f"Тик анализа рынка для {len(users)} пользователей (UTC {now})...")
    expire_old_signals()

    from telegram import Bot
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)

    for user in users:
        tf = getattr(user, "timeframe", None) or config.TIMEFRAME
        minutes = config.SUPPORTED_TIMEFRAMES.get(tf, 15)
        last = getattr(user, "last_market_analysis_at", None)
        if last is not None and (now - last).total_seconds() < minutes * 60:
            continue

        for symbol in config.TRADING_SYMBOLS:
            gen = generate_signal(symbol, user=user)
            if gen is None:
                continue
            signal, trigger_reason = gen

            text = format_signal_card(
                signal,
                leverage=getattr(user, "leverage", 1),
                trigger_reason=trigger_reason,
            )
            keyboard = build_signal_keyboard(signal.id)

            try:
                msg = await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                repository.update_signal_status(
                    signal.id, SignalStatus.PENDING, telegram_message_id=msg.message_id
                )
                logger.info(f"Сигнал #{signal.id} → user {user.telegram_id} [{tf}]")
            except Exception as e:
                logger.error(f"Ошибка отправки сигнала user {user.telegram_id}: {e}")

        repository.touch_user_last_analysis(user.telegram_id)


async def monitor_positions() -> None:
    """Проверка открытых позиций — каждые 2 минуты."""
    await check_positions()


async def weekly_report() -> None:
    """Еженедельный отчёт — каждое воскресенье в 20:00 UTC."""
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

    from telegram import Bot
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    for user in repository.get_active_users():
        try:
            await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка отправки отчёта user {user.telegram_id}: {e}")


def reschedule_analysis(minutes: int) -> None:
    """Совместимость: таймфрейм хранится в users.timeframe; job всегда раз в минуту."""
    global _scheduler
    if _scheduler and _scheduler.get_job("analyze_market"):
        _scheduler.reschedule_job("analyze_market", trigger="interval", minutes=1)
        logger.info("Планировщик: тик 1 мин (интервал анализа — в настройках пользователя)")


def build_scheduler() -> AsyncIOScheduler:
    global _scheduler

    tick_min = min(config.SUPPORTED_TIMEFRAMES.values())

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(analyze_market, "interval", minutes=tick_min, id="analyze_market")
    _scheduler.add_job(monitor_positions, "interval", minutes=2, id="monitor_positions")
    _scheduler.add_job(weekly_report, "cron", day_of_week="sun", hour=20, minute=0, id="weekly_report")

    logger.info(f"Планировщик: тик каждые {tick_min} мин; таймфрейм — у каждого пользователя в БД")
    return _scheduler
