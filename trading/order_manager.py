from loguru import logger

from database import repository
from database.models import Signal, SignalDirection, Trade, TradeStatus
from trading.exchange import (
    place_market_order,
    place_stop_loss_order,
    place_take_profit_order,
)


async def execute_signal(signal: Signal) -> Trade:
    """
    Исполнить сигнал: открыть позицию и выставить SL/TP на бирже.
    Возвращает созданную запись Trade.
    """
    is_long = signal.direction == SignalDirection.LONG
    entry_side = "buy" if is_long else "sell"
    exit_side = "sell" if is_long else "buy"

    logger.info(
        f"Исполняю сигнал #{signal.id}: {signal.symbol} {signal.direction.value} "
        f"${signal.entry_price}"
    )

    # Открываем рыночный ордер
    entry_order = place_market_order(signal.symbol, entry_side, signal.position_size_usdt / signal.entry_price)
    actual_entry_price = float(entry_order.get("average") or entry_order.get("price") or signal.entry_price)
    quantity = float(entry_order.get("filled") or signal.position_size_usdt / signal.entry_price)

    # Выставляем Stop Loss
    sl_order = place_stop_loss_order(signal.symbol, exit_side, quantity, signal.stop_loss)

    # Выставляем Take Profit
    tp_order = place_take_profit_order(signal.symbol, exit_side, quantity, signal.take_profit)

    # Сохраняем сделку в БД
    trade = Trade(
        signal_id=signal.id,
        symbol=signal.symbol,
        direction=signal.direction,
        status=TradeStatus.OPEN,
        entry_price=actual_entry_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        position_size_usdt=signal.position_size_usdt,
        quantity=quantity,
        exchange_order_id=str(entry_order["id"]),
        exchange_sl_order_id=str(sl_order["id"]),
        exchange_tp_order_id=str(tp_order["id"]),
    )

    saved_trade = repository.save_trade(trade)
    logger.info(f"Сделка #{saved_trade.id} открыта: {signal.symbol} @ ${actual_entry_price:.2f}")
    return saved_trade
