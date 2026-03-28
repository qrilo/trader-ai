import asyncio

from loguru import logger

from database import repository
from database.models import SignalDirection, Trade, TradeStatus
from trading.exchange import cancel_order, get_order_status


async def check_positions() -> None:
    """
    Проверить все открытые позиции.
    Вызывается по расписанию каждые несколько минут.
    """
    open_trades = repository.get_open_trades()
    if not open_trades:
        return

    logger.debug(f"Проверка {len(open_trades)} открытых позиций...")
    tasks = [_check_single_trade(trade) for trade in open_trades]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _check_single_trade(trade: Trade) -> None:
    """Проверить статус одной сделки через API биржи."""
    try:
        # Проверяем сработал ли TP
        tp_status = get_order_status(trade.symbol, trade.exchange_tp_order_id)
        if tp_status["status"] == "closed":
            await _close_trade(trade, tp_status, TradeStatus.CLOSED_TP)
            return

        # Проверяем сработал ли SL
        sl_status = get_order_status(trade.symbol, trade.exchange_sl_order_id)
        if sl_status["status"] == "closed":
            await _close_trade(trade, sl_status, TradeStatus.CLOSED_SL)
            return

    except Exception as e:
        logger.error(f"Ошибка проверки сделки #{trade.id}: {e}")


async def _close_trade(trade: Trade, closed_order: dict, status: TradeStatus) -> None:
    """Закрыть сделку в БД и отправить уведомление в Telegram."""
    exit_price = float(closed_order.get("average") or closed_order.get("price") or 0)
    is_long = trade.direction == SignalDirection.LONG

    # Отменяем оставшийся ордер (если сработал TP — отменяем SL и наоборот)
    try:
        if status == TradeStatus.CLOSED_TP:
            cancel_order(trade.symbol, trade.exchange_sl_order_id)
        else:
            cancel_order(trade.symbol, trade.exchange_tp_order_id)
    except Exception as e:
        logger.warning(f"Не удалось отменить противоположный ордер: {e}")

    # Считаем PnL
    if is_long:
        pnl_usdt = (exit_price - trade.entry_price) * trade.quantity
    else:
        pnl_usdt = (trade.entry_price - exit_price) * trade.quantity

    pnl_percent = pnl_usdt / trade.position_size_usdt * 100

    repository.close_trade(
        trade_id=trade.id,
        exit_price=exit_price,
        status=status,
        pnl_usdt=round(pnl_usdt, 2),
        pnl_percent=round(pnl_percent, 2),
    )

    result = "ПРИБЫЛЬ ✅" if status == TradeStatus.CLOSED_TP else "УБЫТОК ❌"
    logger.info(
        f"Сделка #{trade.id} закрыта — {result}: "
        f"{trade.symbol} PnL=${pnl_usdt:+.2f} ({pnl_percent:+.1f}%)"
    )

    await _send_trade_result_notification(trade, exit_price, pnl_usdt, pnl_percent, status)


async def _send_trade_result_notification(
    trade: Trade,
    exit_price: float,
    pnl_usdt: float,
    pnl_percent: float,
    status: TradeStatus,
) -> None:
    """Отправить уведомление о результате сделки в Telegram."""
    from database.models import Trade as TradeModel
    from database import repository
    from signals.formatter import format_trade_result
    from bot.notifications import send_message

    trade.exit_price = exit_price
    trade.pnl_usdt = pnl_usdt
    trade.pnl_percent = pnl_percent
    trade.status = status

    stats = repository.get_statistics()
    text = format_trade_result(trade, stats)
    await send_message(text)
