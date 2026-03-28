from database.models import Signal, SignalDirection, Statistics, Trade, TradeStatus


def format_signal_card(
    signal: Signal,
    leverage: int = 1,
    trigger_reason: str | None = None,
) -> str:
    """Форматировать карточку сигнала для Telegram."""
    direction_emoji = "📈" if signal.direction == SignalDirection.LONG else "📉"
    direction_text = "LONG (покупка)" if signal.direction == SignalDirection.LONG else "SHORT (продажа)"

    sl_pct = abs(signal.stop_loss - signal.entry_price) / signal.entry_price * 100
    tp_pct = abs(signal.take_profit - signal.entry_price) / signal.entry_price * 100

    notional = signal.position_size_usdt * leverage
    sentiment_text = _format_sentiment(signal.sentiment_score)
    confidence_bar = _confidence_bar(signal.ml_confidence)

    size_line = (
        f"💰 Маржа: <b>${signal.position_size_usdt:,.0f}</b>  ⚡️ {leverage}×  "
        f"→ notional <b>${notional:,.0f}</b>"
        if leverage > 1
        else f"💰 Размер:      <b>${signal.position_size_usdt:,.0f}</b>"
    )

    why_block = ""
    if trigger_reason:
        why_block = f"💡 <b>Почему сработало</b>\n{trigger_reason}\n\n"

    return (
        f"🔔 <b>Новый сигнал: {signal.symbol} {direction_text}</b>\n"
        f"{why_block}"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{direction_emoji} Вход:         <b>${signal.entry_price:,.2f}</b>\n"
        f"🛑 Stop Loss:   <b>${signal.stop_loss:,.2f}</b>  (-{sl_pct:.1f}%)\n"
        f"🎯 Take Profit: <b>${signal.take_profit:,.2f}</b>  (+{tp_pct:.1f}%)\n"
        f"{size_line}\n"
        f"📊 R/R:         <b>1 : {signal.risk_reward_ratio:.1f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Уверенность: {confidence_bar} {signal.ml_confidence:.0%}\n"
        f"📰 Сентимент:   {sentiment_text}\n"
        f"⚙️ RSI: {signal.rsi:.0f}  |  Объём: {_format_volume(signal.volume_change)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ Сигнал активен <b>10 минут</b>\n"
        f"🆔 #{signal.id}"
    )


def format_trade_result(trade: Trade, stats: Statistics) -> str:
    """Форматировать уведомление о закрытой сделке."""
    is_win = trade.status == TradeStatus.CLOSED_TP
    emoji = "✅" if is_win else "❌"
    result_text = "ПРИБЫЛЬ" if is_win else "УБЫТОК"
    close_reason = "Take Profit" if is_win else "Stop Loss"

    pnl_sign = "+" if trade.pnl_usdt >= 0 else ""
    duration = _format_duration(trade)
    win_rate = stats.win_rate * 100

    return (
        f"{emoji} <b>Сделка закрыта — {result_text}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 {trade.symbol} {trade.direction.value}\n"
        f"📈 Вход:   <b>${trade.entry_price:,.2f}</b>\n"
        f"🏁 Выход:  <b>${trade.exit_price:,.2f}</b> ({close_reason})\n"
        f"💵 Результат: <b>{pnl_sign}${trade.pnl_usdt:,.2f}  ({pnl_sign}{trade.pnl_percent:.1f}%)</b>\n"
        f"⏱ Время в сделке: {duration}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Статистика за всё время:</b>\n"
        f"Сделок: {stats.total_trades}  |  "
        f"Побед: {stats.winning_trades} ({win_rate:.0f}%)\n"
        f"Общий PnL: <b>${stats.total_pnl_usdt:+,.2f}</b>"
    )


def format_weekly_report(stats: Statistics, week_trades: list[Trade]) -> str:
    """Форматировать еженедельный отчёт."""
    if not week_trades:
        return "📊 <b>Отчёт за неделю</b>\n\nСделок на этой неделе не было."

    week_pnl = sum(t.pnl_usdt for t in week_trades if t.pnl_usdt)
    week_wins = sum(1 for t in week_trades if t.status == TradeStatus.CLOSED_TP)
    week_losses = sum(1 for t in week_trades if t.status == TradeStatus.CLOSED_SL)
    week_winrate = week_wins / len(week_trades) * 100 if week_trades else 0

    best = max(week_trades, key=lambda t: t.pnl_usdt or 0, default=None)
    worst = min(week_trades, key=lambda t: t.pnl_usdt or 0, default=None)

    return (
        f"📈 <b>Еженедельный отчёт</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Сделок за неделю:  {len(week_trades)}\n"
        f"  ✅ Прибыльных:   {week_wins} ({week_winrate:.0f}%)\n"
        f"  ❌ Убыточных:    {week_losses}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 PnL за неделю:  <b>${week_pnl:+,.2f}</b>\n"
        + (f"📊 Лучшая сделка:  {best.symbol} <b>${best.pnl_usdt:+,.2f}</b>\n" if best else "")
        + (f"💩 Худшая сделка:  {worst.symbol} <b>${worst.pnl_usdt:+,.2f}</b>\n" if worst else "")
        + f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Всё время:</b>\n"
        f"Сделок: {stats.total_trades}  |  "
        f"Winrate: {stats.win_rate * 100:.0f}%  |  "
        f"PnL: <b>${stats.total_pnl_usdt:+,.2f}</b>"
    )


def _format_sentiment(score: float) -> str:
    if score is None:
        return "Нет данных"
    if score > 0.2:
        return f"🟢 Позитивный ({score:+.2f})"
    elif score < -0.2:
        return f"🔴 Негативный ({score:+.2f})"
    return f"⚪️ Нейтральный ({score:+.2f})"


def _confidence_bar(confidence: float) -> str:
    filled = round(confidence * 10)
    return "▓" * filled + "░" * (10 - filled)


def _format_volume(volume_change: float) -> str:
    if volume_change is None:
        return "—"
    pct = volume_change * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.0f}%"


def _format_duration(trade: Trade) -> str:
    if not trade.closed_at or not trade.created_at:
        return "—"
    delta = trade.closed_at - trade.created_at
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes = remainder // 60
    if hours > 0:
        return f"{hours}ч {minutes}мин"
    return f"{minutes} мин"
