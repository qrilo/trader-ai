from loguru import logger
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import config
from database import repository
from signals.formatter import format_signal_card, format_weekly_report


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["💼 Баланс", "📊 Статистика"],
        ["📌 Позиции", "📜 История"],
        ["📋 Отчёт за неделю", "⚙️ Настройки"],
        ["❓ Помощь"],
    ],
    resize_keyboard=True,
)

SETUP_KEYBOARD = ReplyKeyboardMarkup(
    [["🔑 Подключить Binance"]],
    resize_keyboard=True,
)


def _get_user_or_none(telegram_id: int):
    if not repository.is_whitelisted(telegram_id):
        return None, "not_whitelisted"
    user = repository.get_user(telegram_id)
    if user is None:
        user = repository.create_user(telegram_id)
    return user, "ok"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    username = update.effective_user.username

    if not repository.is_whitelisted(telegram_id):
        await update.message.reply_text("⛔️ Нет доступа. Обратитесь к администратору.")
        return

    user = repository.get_user(telegram_id)
    if user is None:
        user = repository.create_user(telegram_id, username)

    if not user.has_api_keys:
        await update.message.reply_text(
            f"👋 Привет! Я TRAIDER — AI-трейдер.\n\n"
            f"Для начала работы подключи свой Binance аккаунт.\n"
            f"Нужны Futures API ключи с правами:\n"
            f"  ✅ Enable Reading\n"
            f"  ✅ Enable Futures\n\n"
            f"Нажми кнопку ниже 👇",
            reply_markup=SETUP_KEYBOARD,
        )
        return

    timeframe = user.timeframe or config.TIMEFRAME
    await update.message.reply_text(
        "🤖 <b>TRAIDER запущен</b>\n\n"
        f"Твой таймфрейм: <b>{timeframe}</b> (можно сменить в ⚙️ Настройки).\n"
        "Когда найду хорошую возможность — пришлю сигнал.\n\n"
        "Используй кнопки ниже 👇",
        parse_mode="HTML",
        reply_markup=MAIN_KEYBOARD,
    )


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    user, status = _get_user_or_none(telegram_id)
    if status == "not_whitelisted":
        await update.message.reply_text("⛔️ Нет доступа.")
        return
    if not user.has_api_keys:
        await update.message.reply_text("🔑 Сначала подключи Binance через /start", reply_markup=SETUP_KEYBOARD)
        return

    await update.message.reply_text("⏳ Запрашиваю баланс...", reply_markup=MAIN_KEYBOARD)
    try:
        from trading.exchange import get_exchange_for_user
        exchange = get_exchange_for_user(user)
        exchange.load_time_difference()
        account = exchange.fetch_balance()

        total = float(account.get("total", {}).get("USDT", 0))
        free = float(account.get("free", {}).get("USDT", 0))
        used = float(account.get("used", {}).get("USDT", 0))

        open_trades = repository.get_open_trades(user_id=telegram_id)
        stats = repository.get_statistics()
        mode = "🧪 Testnet" if config.BINANCE_TESTNET else "💰 Реальный счёт"

        await update.message.reply_html(
            f"💼 <b>Фьючерсный кошелёк</b>  {mode}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Всего:       <b>${total:,.2f} USDT</b>\n"
            f"✅ Доступно:    <b>${free:,.2f} USDT</b>\n"
            f"🔒 В позициях:  <b>${used:,.2f} USDT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 Открытых позиций: {len(open_trades)}/{user.max_open_positions}\n"
            f"📊 Общий PnL бота:   <b>${stats.total_pnl_usdt:+,.2f}</b>",
            reply_markup=MAIN_KEYBOARD,
        )
    except Exception as e:
        logger.error(f"Ошибка получения баланса: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=MAIN_KEYBOARD)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not repository.is_whitelisted(update.effective_user.id):
        return
    stats = repository.get_statistics()
    if stats.total_trades == 0:
        await update.message.reply_text("📊 Сделок пока нет.", reply_markup=MAIN_KEYBOARD)
        return

    win_rate = stats.win_rate * 100
    await update.message.reply_html(
        f"📊 <b>Статистика</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Сигналов всего:  {stats.total_signals}\n"
        f"Всего сделок:    {stats.total_trades}\n"
        f"✅ Прибыльных:   {stats.winning_trades} ({win_rate:.0f}%)\n"
        f"❌ Убыточных:    {stats.losing_trades}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Общий PnL: <b>${stats.total_pnl_usdt:+,.2f}</b>\n"
        f"📈 Лучшая:    ${stats.best_trade_pnl:+,.2f}\n"
        f"📉 Худшая:    ${stats.worst_trade_pnl:+,.2f}",
        reply_markup=MAIN_KEYBOARD,
    )


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not repository.is_whitelisted(update.effective_user.id):
        return
    trades = repository.get_open_trades(user_id=update.effective_user.id)
    if not trades:
        await update.message.reply_text("📭 Открытых позиций нет.", reply_markup=MAIN_KEYBOARD)
        return

    lines = ["📌 <b>Открытые позиции:</b>\n"]
    for trade in trades:
        lines.append(
            f"• {trade.symbol} {trade.direction.value}\n"
            f"  Вход: ${trade.entry_price:,.2f}  "
            f"SL: ${trade.stop_loss:,.2f}  "
            f"TP: ${trade.take_profit:,.2f}"
        )
    await update.message.reply_html("\n".join(lines), reply_markup=MAIN_KEYBOARD)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not repository.is_whitelisted(update.effective_user.id):
        return
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from database.models import Trade
    from database.repository import engine

    week_ago = datetime.utcnow() - timedelta(days=7)
    with Session(engine) as session:
        week_trades = list(session.scalars(
            select(Trade).where(Trade.created_at >= week_ago)
        ).all())

    stats = repository.get_statistics()
    text = format_weekly_report(stats, week_trades)
    await update.message.reply_html(text, reply_markup=MAIN_KEYBOARD)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    if not repository.is_whitelisted(telegram_id):
        return

    signals = repository.get_recent_signals(telegram_id, limit=20)
    if not signals:
        await update.message.reply_text("📜 Истории сигналов пока нет.", reply_markup=MAIN_KEYBOARD)
        return

    from database.models import SignalStatus, TradeStatus

    STATUS_ICON = {
        SignalStatus.PENDING:   "⏳",
        SignalStatus.APPROVED:  "✅",
        SignalStatus.REJECTED:  "🚫",
        SignalStatus.EXPIRED:   "⌛",
        SignalStatus.CANCELLED: "❌",
    }

    lines = ["📜 <b>История сигналов</b>\n"]
    for s in signals:
        icon = STATUS_ICON.get(s.status, "•")
        dir_icon = "📈" if s.direction.value == "LONG" else "📉"
        date = s.created_at.strftime("%d.%m %H:%M")

        tf = f"[{s.timeframe}]" if s.timeframe else ""
        line = f"{icon} {dir_icon} <b>{s.symbol}</b> {s.direction.value} {tf}  <i>{date}</i>"

        if s.trade and s.trade.pnl_usdt is not None:
            pnl = s.trade.pnl_usdt
            pnl_icon = "🟢" if pnl >= 0 else "🔴"
            line += f"\n   {pnl_icon} PnL: <b>${pnl:+.2f}</b> ({s.trade.pnl_percent:+.1f}%)"
        elif s.status == SignalStatus.APPROVED and s.trade:
            line += "\n   🔵 В позиции"

        lines.append(line)

    await update.message.reply_html("\n\n".join(lines), reply_markup=MAIN_KEYBOARD)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    if not repository.is_whitelisted(telegram_id):
        return
    user = repository.get_user(telegram_id)
    if not user:
        return
    from bot.handlers import build_settings_keyboard, settings_text
    timeframe = user.timeframe or config.TIMEFRAME
    await update.message.reply_html(
        settings_text(user, timeframe),
        reply_markup=build_settings_keyboard(user, timeframe),
    )


async def handle_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    text = update.message.text

    # Обработка состояний регистрации (ввод API ключей)
    state = context.user_data.get("state")
    if state == "awaiting_api_key":
        await _handle_api_key_input(update, context)
        return
    if state == "awaiting_api_secret":
        await _handle_api_secret_input(update, context)
        return

    if text == "🔑 Подключить Binance":
        await _start_api_setup(update, context)
    elif text == "💼 Баланс":
        await balance_command(update, context)
    elif text == "📊 Статистика":
        await stats_command(update, context)
    elif text == "📌 Позиции":
        await positions_command(update, context)
    elif text == "📜 История":
        await history_command(update, context)
    elif text == "📋 Отчёт за неделю":
        await report_command(update, context)
    elif text == "⚙️ Настройки":
        await settings_command(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    else:
        user, status = _get_user_or_none(telegram_id)
        if status == "ok" and user and user.has_api_keys:
            await update.message.reply_text(
                "Не понял сообщение. Используй кнопки внизу или команды:\n"
                "/balance /stats /positions /history /report /settings",
                reply_markup=MAIN_KEYBOARD,
            )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not repository.is_whitelisted(update.effective_user.id):
        await update.message.reply_text("⛔️ Нет доступа.")
        return
    await update.message.reply_html(
        "❓ <b>Справка TRAIDER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Кнопки</b> — быстрый доступ к тому же, что и команды:\n"
        "💼 Баланс · 📊 Статистика · 📌 Позиции · 📜 История\n"
        "📋 Отчёт за неделю · ⚙️ Настройки (по разделам)\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Команды</b> (можно набрать вручную):\n"
        "/start — приветствие и клавиатура\n"
        "/help — эта справка\n"
        "/balance — баланс фьючерсного кошелька\n"
        "/stats — сделки и PnL\n"
        "/positions — открытые позиции\n"
        "/history — история сигналов\n"
        "/report — отчёт за 7 дней\n"
        "/settings — настройки\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Когда придёт <b>сигнал</b>, нажми «Войти» или «Пропустить» под сообщением.",
        reply_markup=MAIN_KEYBOARD,
    )


async def _start_api_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["state"] = "awaiting_api_key"
    await update.message.reply_text(
        "🔑 <b>Подключение Binance</b>\n\n"
        "Шаг 1/2: Отправь свой <b>API Key</b>\n\n"
        "⚠️ Отправляй только в личном чате с ботом!\n"
        "Нужны права: Enable Reading + Enable Futures",
        parse_mode="HTML",
    )


async def _handle_api_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    api_key = update.message.text.strip()
    if len(api_key) < 10:
        await update.message.reply_text("❌ Некорректный API Key. Попробуй ещё раз.")
        return

    context.user_data["pending_api_key"] = api_key
    context.user_data["state"] = "awaiting_api_secret"

    await update.message.reply_text(
        "✅ API Key получен.\n\n"
        "Шаг 2/2: Теперь отправь <b>API Secret</b>",
        parse_mode="HTML",
    )


async def _handle_api_secret_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    api_secret = update.message.text.strip()
    api_key = context.user_data.get("pending_api_key", "")
    telegram_id = update.effective_user.id

    if len(api_secret) < 10:
        await update.message.reply_text("❌ Некорректный Secret. Попробуй ещё раз.")
        return

    # Проверяем ключи подключившись к Binance
    await update.message.reply_text("⏳ Проверяю подключение к Binance...")
    try:
        from trading.exchange import get_exchange
        exchange = get_exchange(api_key=api_key, api_secret=api_secret)
        exchange.load_time_difference()
        balance = exchange.fetch_balance()
        usdt = float(balance.get("total", {}).get("USDT", 0))
    except Exception as e:
        context.user_data.clear()
        await update.message.reply_text(
            f"❌ <b>Ошибка подключения к Binance</b>\n\n{e}\n\n"
            "Проверь ключи и попробуй снова через /start",
            parse_mode="HTML",
        )
        return

    repository.update_user_keys(telegram_id, api_key, api_secret)
    context.user_data.clear()

    await update.message.reply_html(
        f"✅ <b>Binance подключён!</b>\n\n"
        f"💵 Баланс USDT: <b>${usdt:,.2f}</b>\n\n"
        f"Теперь я буду присылать тебе сигналы.\n"
        f"Используй кнопки ниже 👇",
        reply_markup=MAIN_KEYBOARD,
    )
    logger.info(f"Пользователь {telegram_id} подключил Binance (баланс ${usdt:.2f})")


def build_application() -> Application:
    from bot.handlers import handle_callback

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons))
    return app
