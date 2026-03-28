"""Текст профиля трейдера для FinBERT и логов."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database.models import User


def format_user_trading_context(user: "User") -> str:
    """
    Контекст на английском (FinBERT обучен на EN) + кратко для логов.
    """
    margin = float(getattr(user, "fixed_position_usdt", 0) or 0) or 50.0
    lev = int(getattr(user, "leverage", 5) or 5)
    sl = float(getattr(user, "sl_percent", 1.5) or 1.5)
    tp = float(getattr(user, "tp_percent", 3.0) or 3.0)
    tf = getattr(user, "timeframe", None) or "15m"
    return (
        f"Trader profile: margin ${margin:.0f} USDT, leverage {lev}x, "
        f"stop-loss {sl:.1f}% from entry, take-profit {tp:.1f}% from entry, "
        f"chart timeframe {tf}. "
    )
