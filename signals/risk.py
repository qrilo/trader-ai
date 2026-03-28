from dataclasses import dataclass

from config import config


@dataclass
class RiskParams:
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_usdt: float
    quantity: float
    risk_reward_ratio: float
    risk_usdt: float


def calculate_risk_params(
    direction: str,
    entry_price: float,
    atr: float,
    balance_usdt: float,
) -> RiskParams:
    """
    Рассчитать SL, TP и размер позиции на основе ATR.

    SL = 1.5 * ATR от точки входа
    TP = SL * MIN_RR_RATIO (минимум 1:2)
    Размер позиции = RISK_PER_TRADE% от баланса / расстояние до SL
    """
    sl_distance = atr * 1.5
    tp_distance = sl_distance * config.MIN_RR_RATIO

    if direction == "LONG":
        stop_loss = entry_price - sl_distance
        take_profit = entry_price + tp_distance
    else:
        stop_loss = entry_price + sl_distance
        take_profit = entry_price - tp_distance

    # Сколько долларов рискуем
    risk_usdt = balance_usdt * config.RISK_PER_TRADE

    # Размер позиции в USDT = риск / % расстояния до SL
    sl_percent = abs(entry_price - stop_loss) / entry_price
    position_size_usdt = risk_usdt / sl_percent
    position_size_usdt = min(position_size_usdt, balance_usdt * 0.2)  # не более 20% баланса

    quantity = position_size_usdt / entry_price

    rr_ratio = abs(take_profit - entry_price) / abs(stop_loss - entry_price)

    return RiskParams(
        entry_price=round(entry_price, 2),
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        position_size_usdt=round(position_size_usdt, 2),
        quantity=round(quantity, 6),
        risk_reward_ratio=round(rr_ratio, 2),
        risk_usdt=round(risk_usdt, 2),
    )
