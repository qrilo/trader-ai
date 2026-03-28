import asyncio
from concurrent.futures import ThreadPoolExecutor

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import config
from database import repository
from database.models import SignalStatus, User


_executor = ThreadPoolExecutor(max_workers=1)


def build_signal_keyboard(signal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Войти", callback_data=f"approve:{signal_id}"),
        InlineKeyboardButton("❌ Пропустить", callback_data=f"reject:{signal_id}"),
    ]])


def settings_text(user: User, timeframe: str) -> str:
    minutes = config.SUPPORTED_TIMEFRAMES.get(timeframe, 15)
    from models.trainer import model_exists
    models_ok = all(model_exists(s, timeframe) for s in config.TRADING_SYMBOLS)
    model_icon = "✅" if models_ok else "❌ не обучена"

    m = float(getattr(user, "fixed_position_usdt", 0) or 0) or config.DEFAULT_MARGIN_USDT
    sl = float(getattr(user, "sl_percent", 0) or 0) or config.DEFAULT_SL_PERCENT
    tp = float(getattr(user, "tp_percent", 0) or 0) or config.DEFAULT_TP_PERCENT

    return (
        f"⚙️ <b>Настройки</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Таймфрейм: <b>{timeframe}</b> (свечи каждые {minutes} мин)\n"
        f"💰 Маржа: <b>${m:.0f} USDT</b>  ·  ⚡️ Плечо: <b>{user.leverage}×</b>\n"
        f"🎯 Стоп / тейк: <b>{sl:.1f}%</b> / <b>{tp:.1f}%</b> от цены входа\n"
        f"📌 Позиций: <b>{user.max_open_positions}</b>\n"
        f"🎯 Порог ML: <b>{user.min_confidence * 100:.0f}%</b>  ·  ⏱ таймаут сигнала: <b>{user.signal_timeout_minutes} мин</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Модель [{timeframe}]: {model_icon}\n"
        f"🔑 Binance: {'✅' if user.has_api_keys else '❌'}\n\n"
        f"<i>Ниже — разделы. Меньше прокрутки, всё по шагам.</i>"
    )


def _btn_back_main() -> InlineKeyboardButton:
    return InlineKeyboardButton("◀️ К сводке", callback_data="s:go:main")


def build_settings_keyboard(user: User, timeframe: str) -> InlineKeyboardMarkup:
    """Главный экран настроек — только переходы в разделы."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱ Таймфрейм", callback_data="s:go:tf"),
            InlineKeyboardButton("💰 Маржа", callback_data="s:go:margin"),
        ],
        [
            InlineKeyboardButton("⚡ Плечо", callback_data="s:go:lev"),
            InlineKeyboardButton("🎯 Стоп / тейк", callback_data="s:go:stops"),
        ],
        [
            InlineKeyboardButton("📌 Лимиты и ML", callback_data="s:go:more"),
        ],
        [InlineKeyboardButton("🔄 Переобучить модель", callback_data="s:retrain")],
        [InlineKeyboardButton("🔑 Сменить API ключи", callback_data="s:change_keys")],
    ])


def _panel_tf_text(user: User, timeframe: str) -> str:
    m = config.SUPPORTED_TIMEFRAMES.get(timeframe, 15)
    return (
        f"⏱ <b>Таймфрейм</b>\n"
        f"Как часто обновляются свечи и какая модель используется.\n"
        f"Сейчас: <b>{timeframe}</b> (анализ не чаще чем раз в {m} мин).\n\n"
        f"<i>Выбери интервал:</i>"
    )


def build_settings_panel_tf(user: User, timeframe: str) -> InlineKeyboardMarkup:
    row = []
    for tf in config.SUPPORTED_TIMEFRAMES:
        label = f"✅ {tf}" if tf == timeframe else tf
        row.append(InlineKeyboardButton(label, callback_data=f"s:tf:{tf}"))
    return InlineKeyboardMarkup([row, [_btn_back_main()]])


def _panel_margin_text(user: User) -> str:
    cur = float(getattr(user, "fixed_position_usdt", 0) or 0) or config.DEFAULT_MARGIN_USDT
    return (
        f"💰 <b>Маржа на сделку</b>\n"
        f"Сколько USDT резервируется под одну позицию (размер входа в USDT).\n"
        f"Сейчас: <b>${cur:.0f}</b>\n\n"
        f"<i>Выбери сумму:</i>"
    )


def build_settings_panel_margin(user: User) -> InlineKeyboardMarkup:
    fixed = float(getattr(user, "fixed_position_usdt", 0) or 0) or config.DEFAULT_MARGIN_USDT
    row = []
    for amt in [20, 50, 100, 200]:
        label = f"✅ ${amt}" if abs(fixed - amt) < 0.01 else f"${amt}"
        row.append(InlineKeyboardButton(label, callback_data=f"s:margin:{amt}"))
    return InlineKeyboardMarkup([row, [_btn_back_main()]])


def _panel_stops_text(user: User) -> str:
    sl = float(getattr(user, "sl_percent", 0) or 0) or config.DEFAULT_SL_PERCENT
    tp = float(getattr(user, "tp_percent", 0) or 0) or config.DEFAULT_TP_PERCENT
    rr = (tp / sl) if sl > 0 else 0
    return (
        f"🎯 <b>Стоп-лосс и тейк-профит</b>\n"
        f"В процентах от цены входа (не от депозита).\n"
        f"Сейчас: SL <b>{sl:.1f}%</b>, TP <b>{tp:.1f}%</b>  →  R/R ≈ <b>1 : {rr:.1f}</b>\n\n"
        f"<i>Пресеты (SL / TP):</i>"
    )


def build_settings_panel_stops(user: User) -> InlineKeyboardMarkup:
    """callback_data s:sltp:X:Y — десятые доли процента (15 = 1.5%)."""
    sl = float(getattr(user, "sl_percent", 0) or 0) or config.DEFAULT_SL_PERCENT
    tp = float(getattr(user, "tp_percent", 0) or 0) or config.DEFAULT_TP_PERCENT

    def _match(a: int, b: int) -> bool:
        return abs(sl * 10 - a) < 0.01 and abs(tp * 10 - b) < 0.01

    presets = [
        (8, 16, "0.8 / 1.6"),
        (10, 20, "1 / 2"),
        (15, 30, "1.5 / 3"),
        (20, 40, "2 / 4"),
    ]
    row = []
    for a, b, label in presets:
        mark = "✅ " if _match(a, b) else ""
        row.append(InlineKeyboardButton(
            f"{mark}{label}",
            callback_data=f"s:sltp:{a}:{b}",
        ))
    return InlineKeyboardMarkup([row, [_btn_back_main()]])


def _panel_lev_text(user: User) -> str:
    return (
        f"⚡ <b>Плечо (leverage)</b>\n"
        f"Устанавливается на Binance перед ордером.\n"
        f"Сейчас: <b>{user.leverage}×</b>\n\n"
        f"<i>Выбери плечо:</i>"
    )


def build_settings_panel_lev(user: User) -> InlineKeyboardMarkup:
    row = []
    for lv in [1, 3, 5, 10, 20]:
        label = f"✅ {lv}×" if user.leverage == lv else f"{lv}×"
        row.append(InlineKeyboardButton(label, callback_data=f"s:lev:{lv}"))
    return InlineKeyboardMarkup([row, [_btn_back_main()]])


def _panel_more_text(user: User) -> str:
    return (
        f"📌 <b>Лимиты и ML</b>\n"
        f"• Макс. позиций — сколько сделок одновременно.\n"
        f"• Порог ML — минимальная уверенность модели для сигнала.\n"
        f"Сейчас: позиций <b>{user.max_open_positions}</b>, ML <b>{user.min_confidence * 100:.0f}%</b>\n\n"
        f"<i>Выбери значения:</i>"
    )


def build_settings_panel_more(user: User) -> InlineKeyboardMarkup:
    pos_row = []
    for p in [1, 2, 3, 5]:
        label = f"✅ {p}" if user.max_open_positions == p else str(p)
        pos_row.append(InlineKeyboardButton(label, callback_data=f"s:pos:{p}"))
    conf_row = []
    cur = round(user.min_confidence * 100)
    for c in [60, 65, 70, 75]:
        label = f"✅ {c}%" if cur == c else f"{c}%"
        conf_row.append(InlineKeyboardButton(label, callback_data=f"s:conf:{c}"))
    return InlineKeyboardMarkup([pos_row, conf_row, [_btn_back_main()]])


async def _render_settings_view(query, user: User, view: str) -> None:
    """Перерисовать экран: main | tf | margin | stops | lev | more"""
    tf = user.timeframe or config.TIMEFRAME
    try:
        if view == "main":
            await query.edit_message_text(
                settings_text(user, tf),
                parse_mode="HTML",
                reply_markup=build_settings_keyboard(user, tf),
            )
        elif view == "tf":
            await query.edit_message_text(
                _panel_tf_text(user, tf),
                parse_mode="HTML",
                reply_markup=build_settings_panel_tf(user, tf),
            )
        elif view == "margin":
            await query.edit_message_text(
                _panel_margin_text(user),
                parse_mode="HTML",
                reply_markup=build_settings_panel_margin(user),
            )
        elif view == "stops":
            await query.edit_message_text(
                _panel_stops_text(user),
                parse_mode="HTML",
                reply_markup=build_settings_panel_stops(user),
            )
        elif view == "lev":
            await query.edit_message_text(
                _panel_lev_text(user),
                parse_mode="HTML",
                reply_markup=build_settings_panel_lev(user),
            )
        elif view == "more":
            await query.edit_message_text(
                _panel_more_text(user),
                parse_mode="HTML",
                reply_markup=build_settings_panel_more(user),
            )
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_id = update.effective_user.id

    if not repository.is_whitelisted(telegram_id):
        await query.answer("⛔️ Нет доступа", show_alert=True)
        return

    await query.answer()

    data = query.data

    if data.startswith("approve:") or data.startswith("reject:"):
        await _handle_trade_action(query, data, telegram_id)

    elif data.startswith("s:"):
        user = repository.get_user(telegram_id)
        if not user:
            return
        await _handle_settings(query, data, user)


async def _handle_trade_action(query, data: str, telegram_id: int) -> None:
    action, signal_id_str = data.split(":")
    signal_id = int(signal_id_str)
    signal = repository.get_signal(signal_id)

    if signal is None:
        await query.edit_message_text("⚠️ Сигнал не найден")
        return

    # Проверяем что сигнал принадлежит этому пользователю
    if signal.user_id is not None and signal.user_id != telegram_id:
        await query.answer("⛔️ Это не ваш сигнал", show_alert=True)
        return

    if signal.status != SignalStatus.PENDING:
        status_text = {
            SignalStatus.APPROVED: "уже исполнен",
            SignalStatus.REJECTED: "уже отклонён",
            SignalStatus.EXPIRED: "истёк",
        }.get(signal.status, "обработан")
        await query.edit_message_text(f"ℹ️ Сигнал #{signal_id} {status_text}")
        return

    if action == "approve":
        await _handle_approve(query, signal_id, signal, telegram_id)
    elif action == "reject":
        await _handle_reject(query, signal_id, signal)


async def _handle_settings(query, data: str, user: User) -> None:
    parts = data.split(":")
    cmd = parts[1]

    if cmd == "go":
        page = parts[2] if len(parts) > 2 else "main"
        user = repository.get_user(user.telegram_id)
        if not user:
            return
        if page not in ("main", "tf", "margin", "stops", "lev", "more"):
            page = "main"
        await _render_settings_view(query, user, page)
        return

    elif cmd == "tf":
        new_tf = parts[2]
        if new_tf not in config.SUPPORTED_TIMEFRAMES:
            return
        old_tf = user.timeframe or config.TIMEFRAME
        if new_tf != old_tf:
            repository.update_user_setting(
                user.telegram_id,
                timeframe=new_tf,
                last_market_analysis_at=None,
            )
            from models.predictor import clear_predictor_cache
            clear_predictor_cache()
        user = repository.get_user(user.telegram_id)
        await _render_settings_view(query, user, "tf")

    elif cmd == "margin":
        amt = float(parts[2])
        repository.update_user_setting(user.telegram_id, fixed_position_usdt=amt)
        user = repository.get_user(user.telegram_id)
        await _render_settings_view(query, user, "margin")

    elif cmd == "sltp":
        sl = int(parts[2]) / 10.0
        tp = int(parts[3]) / 10.0
        repository.update_user_setting(
            user.telegram_id,
            sl_percent=sl,
            tp_percent=tp,
        )
        user = repository.get_user(user.telegram_id)
        await _render_settings_view(query, user, "stops")

    elif cmd == "lev":
        repository.update_user_setting(user.telegram_id, leverage=int(parts[2]))
        user = repository.get_user(user.telegram_id)
        await _render_settings_view(query, user, "lev")

    elif cmd == "pos":
        repository.update_user_setting(user.telegram_id, max_open_positions=int(parts[2]))
        user = repository.get_user(user.telegram_id)
        await _render_settings_view(query, user, "more")

    elif cmd == "conf":
        conf = int(parts[2]) / 100
        repository.update_user_setting(user.telegram_id, min_confidence=conf)
        user = repository.get_user(user.telegram_id)
        await _render_settings_view(query, user, "more")

    elif cmd == "retrain":
        tf = user.timeframe or config.TIMEFRAME
        await query.edit_message_text(
            f"🔄 <b>Запускаю переобучение</b> [{tf}]\n\n"
            "Это займёт 5-15 минут. Пришлю уведомление когда закончу.",
            parse_mode="HTML",
        )
        loop = asyncio.get_event_loop()
        loop.run_in_executor(_executor, _retrain_background, tf, user.telegram_id)
        return

    elif cmd == "change_keys":
        await query.edit_message_text(
            "🔑 Для смены API ключей напиши /start",
            parse_mode="HTML",
        )
        return


def _retrain_background(timeframe: str, chat_id: int) -> None:
    import asyncio as _asyncio
    from telegram import Bot

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    try:
        from models.trainer import train_all
        train_all(force=True, timeframe=timeframe)
        from models.predictor import clear_predictor_cache
        clear_predictor_cache()
        _asyncio.run(bot.send_message(
            chat_id=chat_id,
            text=f"✅ <b>Переобучение завершено!</b>\nМодель [{timeframe}] готова.",
            parse_mode="HTML",
        ))
    except Exception as e:
        logger.error(f"Ошибка фонового переобучения: {e}")
        _asyncio.run(bot.send_message(
            chat_id=chat_id,
            text=f"❌ <b>Ошибка переобучения</b>\n{e}",
            parse_mode="HTML",
        ))


async def _handle_approve(query, signal_id: int, signal, telegram_id: int) -> None:
    from trading.order_manager import execute_signal

    logger.info(f"Пользователь {telegram_id} апрувнул сигнал #{signal_id}")
    await query.edit_message_text(
        f"⏳ Исполняю ордер {signal.symbol} {signal.direction.value}...",
    )

    try:
        user = repository.get_user(telegram_id)
        trade = await execute_signal(signal, user=user)
        repository.update_signal_status(signal_id, SignalStatus.APPROVED)

        await query.edit_message_text(
            f"✅ <b>Ордер исполнен!</b>\n\n"
            f"📌 {signal.symbol} {signal.direction.value}\n"
            f"📈 Вход: <b>${trade.entry_price:,.2f}</b>\n"
            f"🛑 SL: <b>${trade.stop_loss:,.2f}</b>\n"
            f"🎯 TP: <b>${trade.take_profit:,.2f}</b>\n\n"
            "Слежу за позицией и сообщу о результате.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Ошибка исполнения сигнала #{signal_id}: {e}")
        await query.edit_message_text(
            f"❌ <b>Ошибка исполнения</b>\n\n{e}",
            parse_mode="HTML",
        )


async def _handle_reject(query, signal_id: int, signal) -> None:
    repository.update_signal_status(signal_id, SignalStatus.REJECTED)
    await query.edit_message_text(
        f"🚫 Сигнал #{signal_id} <b>{signal.symbol} {signal.direction.value}</b> отклонён",
        parse_mode="HTML",
    )
