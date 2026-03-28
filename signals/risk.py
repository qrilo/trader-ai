from dataclasses import dataclass


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
    margin_usdt: float,
    sl_percent: float,
    tp_percent: float,
) -> RiskParams:
    """
    SL/TP от цены входа в процентах; position_size_usdt = маржа (USDT на сделку).
    """
    sl_frac = sl_percent / 100.0
    tp_frac = tp_percent / 100.0

    if direction == "LONG":
        stop_loss = entry_price * (1 - sl_frac)
        take_profit = entry_price * (1 + tp_frac)
    else:
        stop_loss = entry_price * (1 + sl_frac)
        take_profit = entry_price * (1 - tp_frac)

    position_size_usdt = margin_usdt
    quantity = margin_usdt / entry_price
    rr_ratio = (tp_percent / sl_percent) if sl_percent > 0 else 0.0
    # Оценка риска в USDT на маржу при срабатывании SL (упрощённо)
    risk_usdt = margin_usdt * sl_frac

    return RiskParams(
        entry_price=round(entry_price, 2),
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        position_size_usdt=round(position_size_usdt, 2),
        quantity=round(quantity, 6),
        risk_reward_ratio=round(rr_ratio, 2),
        risk_usdt=round(risk_usdt, 2),
    )
