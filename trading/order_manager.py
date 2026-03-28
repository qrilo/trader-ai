from loguru import logger

from database import repository
from database.models import Signal, SignalDirection, Trade, TradeStatus, User
from trading.exchange import get_exchange_for_user, set_leverage


def _adjust_to_min_order(exchange, symbol: str, quantity: float, entry_price: float) -> float:
    """
    Если quantity меньше минимального лота Binance — поднять до минимума.
    Если баланс не покрывает даже минимум — выбросить понятную ошибку.
    """
    try:
        markets = exchange.load_markets()
        market = markets.get(symbol, {})
        limits = market.get("limits", {})
        min_amount = limits.get("amount", {}).get("min") or 0
        precision = market.get("precision", {}).get("amount") or 0.001

        if min_amount and quantity < min_amount:
            logger.warning(
                f"Позиция {quantity:.6f} < минимум {min_amount} — "
                f"автоматически увеличена до минимального лота"
            )
            quantity = min_amount

        # Округляем до нужной точности
        if precision:
            import math
            decimals = max(0, -int(math.floor(math.log10(precision))))
            quantity = round(quantity, decimals)

    except Exception as e:
        logger.warning(f"Не удалось проверить минимальный размер: {e}")

    return quantity


async def execute_signal(signal: Signal, user: User = None) -> Trade:
    """
    Исполнить сигнал: открыть позицию и выставить SL/TP на бирже пользователя.
    """
    if user is None:
        if signal.user_id:
            user = repository.get_user(signal.user_id)
        if user is None:
            raise ValueError("Пользователь не найден для исполнения сигнала")

    exchange = get_exchange_for_user(user)
    exchange.load_time_difference()

    leverage = getattr(user, "leverage", 5)
    set_leverage(exchange, signal.symbol, leverage)

    is_long = signal.direction == SignalDirection.LONG
    entry_side = "buy" if is_long else "sell"
    exit_side = "sell" if is_long else "buy"

    # При плече>1 маржа = position_size_usdt, notional = position_size_usdt * leverage
    notional_usdt = signal.position_size_usdt * leverage
    quantity = notional_usdt / signal.entry_price

    # Поднимаем до минимального лота если нужно
    quantity = _adjust_to_min_order(exchange, signal.symbol, quantity, signal.entry_price)

    logger.info(
        f"Исполняю #{signal.id}: {signal.symbol} {signal.direction.value} "
        f"qty={quantity:.6f} маржа=${signal.position_size_usdt:.2f} "
        f"notional=${notional_usdt:.2f} плечо={leverage}× (user={user.telegram_id})"
    )

    entry_order = exchange.create_order(signal.symbol, "market", entry_side, quantity)
    actual_entry_price = float(entry_order.get("average") or entry_order.get("price") or signal.entry_price)
    actual_quantity = float(entry_order.get("filled") or quantity)

    sl_order = exchange.create_order(
        signal.symbol, "stop_market", exit_side, actual_quantity,
        params={"stopPrice": signal.stop_loss, "reduceOnly": True},
    )

    tp_order = exchange.create_order(
        signal.symbol, "take_profit_market", exit_side, actual_quantity,
        params={"stopPrice": signal.take_profit, "reduceOnly": True},
    )

    trade = Trade(
        signal_id=signal.id,
        user_id=user.telegram_id,
        symbol=signal.symbol,
        direction=signal.direction,
        status=TradeStatus.OPEN,
        entry_price=actual_entry_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        position_size_usdt=signal.position_size_usdt,
        quantity=actual_quantity,
        exchange_order_id=str(entry_order["id"]),
        exchange_sl_order_id=str(sl_order["id"]),
        exchange_tp_order_id=str(tp_order["id"]),
    )

    saved_trade = repository.save_trade(trade)
    logger.info(f"Сделка #{saved_trade.id}: {signal.symbol} @ ${actual_entry_price:.2f}")
    return saved_trade
