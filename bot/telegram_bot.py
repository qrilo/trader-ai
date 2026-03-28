from loguru import logger
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from config import config
from database import repository
from signals.formatter import format_signal_card, format_weekly_report


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 <b>TRAIDER запущен</b>\n\n"
        "Анализирую рынок каждые 15 минут.\n"
        "Когда найду хорошую возможность — пришлю сигнал.\n\n"
        "Команды:\n"
        "/balance — баланс фьючерсного кошелька\n"
        "/stats — статистика всех сделок\n"
        "/positions — открытые позиции\n"
        "/report — отчёт за неделю",
        parse_mode="HTML",
    )


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from data.collector import get_account_balance
    from trading.exchange import get_exchange

    await update.message.reply_text("⏳ Запрашиваю баланс...")

    try:
        balance = get_account_balance()
        exchange = get_exchange()
        account = exchange.fetch_balance()

        total = float(account.get("total", {}).get("USDT", 0))
        free = float(account.get("free", {}).get("USDT", 0))
        used = float(account.get("used", {}).get("USDT", 0))

        open_trades = repository.get_open_trades()
        stats = repository.get_statistics()
        mode = "🧪 Testnet" if config.BINANCE_TESTNET else "💰 Реальный счёт"

        await update.message.reply_html(
            f"💼 <b>Фьючерсный кошелёк</b>  {mode}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Всего:       <b>${total:,.2f} USDT</b>\n"
            f"✅ Доступно:    <b>${free:,.2f} USDT</b>\n"
            f"🔒 В позициях:  <b>${used:,.2f} USDT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 Открытых позиций: {len(open_trades)}/{config.MAX_OPEN_POSITIONS}\n"
            f"📊 Общий PnL бота:   <b>${stats.total_pnl_usdt:+,.2f}</b>"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка получения баланса: {e}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = repository.get_statistics()
    if stats.total_trades == 0:
        await update.message.reply_text("📊 Сделок пока нет.")
        return

    win_rate = stats.win_rate * 100
    await update.message.reply_html(
        f"📊 <b>Статистика</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Всего сделок:    {stats.total_trades}\n"
        f"✅ Прибыльных:   {stats.winning_trades} ({win_rate:.0f}%)\n"
        f"❌ Убыточных:    {stats.losing_trades}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Общий PnL: <b>${stats.total_pnl_usdt:+,.2f}</b>\n"
        f"📈 Лучшая:    ${stats.best_trade_pnl:+,.2f}\n"
        f"📉 Худшая:    ${stats.worst_trade_pnl:+,.2f}"
    )


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    trades = repository.get_open_trades()
    if not trades:
        await update.message.reply_text("📭 Открытых позиций нет.")
        return

    lines = ["📌 <b>Открытые позиции:</b>\n"]
    for trade in trades:
        lines.append(
            f"• {trade.symbol} {trade.direction.value}\n"
            f"  Вход: ${trade.entry_price:,.2f}  "
            f"SL: ${trade.stop_loss:,.2f}  "
            f"TP: ${trade.take_profit:,.2f}"
        )
    await update.message.reply_html("\n".join(lines))


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from database.models import Trade, TradeStatus
    from database.repository import engine

    week_ago = datetime.utcnow() - timedelta(days=7)
    with Session(engine) as session:
        week_trades = list(session.scalars(
            select(Trade).where(Trade.created_at >= week_ago)
        ).all())

    stats = repository.get_statistics()
    text = format_weekly_report(stats, week_trades)
    await update.message.reply_html(text)


def build_application() -> Application:
    from bot.handlers import handle_callback

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    return app
