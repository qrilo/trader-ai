from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import create_engine, inspect, select, text, update
from sqlalchemy.orm import Session

from config import config
from database.models import Base, Settings, Signal, SignalStatus, Statistics, Trade, TradeStatus, User


engine = create_engine(config.DATABASE_URL)


def _ensure_user_columns() -> None:
    """Добавить колонки при обновлении схемы без Alembic."""
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("users")}
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if "sl_percent" not in cols:
            if dialect == "postgresql":
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN sl_percent DOUBLE PRECISION DEFAULT 1.5"
                ))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN sl_percent REAL DEFAULT 1.5"))
        if "tp_percent" not in cols:
            if dialect == "postgresql":
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN tp_percent DOUBLE PRECISION DEFAULT 3.0"
                ))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN tp_percent REAL DEFAULT 3.0"))

        # Старый режим «% от баланса» — колонка больше не в модели
        if "risk_per_trade" in cols:
            try:
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE users DROP COLUMN risk_per_trade"))
                else:
                    conn.execute(text("ALTER TABLE users DROP COLUMN risk_per_trade"))
            except Exception as e:
                logger.warning(
                    "Не удалось удалить колонку risk_per_trade (можно проигнорировать на старом SQLite): {}",
                    e,
                )


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_user_columns()
    with Session(engine) as session:
        if not session.scalar(select(Statistics)):
            session.add(Statistics())
        session.commit()


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = None) -> Optional[str]:
    with Session(engine) as session:
        row = session.get(Settings, key)
        return row.value if row else default


def set_setting(key: str, value: str) -> None:
    with Session(engine) as session:
        row = session.get(Settings, key)
        if row:
            row.value = value
        else:
            session.add(Settings(key=key, value=value))
        session.commit()


# ── Users ─────────────────────────────────────────────────────────────────────

def get_user(telegram_id: int) -> Optional[User]:
    with Session(engine) as session:
        return session.get(User, telegram_id)


def get_active_users() -> list[User]:
    """Все активные пользователи с настроенными API ключами."""
    with Session(engine) as session:
        return list(session.scalars(
            select(User).where(
                User.is_active == True,
                User.binance_api_key_enc.is_not(None),
                User.binance_api_secret_enc.is_not(None),
            )
        ).all())


def create_user(telegram_id: int, username: str = None) -> User:
    with Session(engine) as session:
        user = User(
            telegram_id=telegram_id,
            username=username,
            timeframe=config.TIMEFRAME,
            fixed_position_usdt=config.DEFAULT_MARGIN_USDT,
            sl_percent=config.DEFAULT_SL_PERCENT,
            tp_percent=config.DEFAULT_TP_PERCENT,
            max_open_positions=config.DEFAULT_MAX_OPEN_POSITIONS,
            min_confidence=config.DEFAULT_MIN_CONFIDENCE,
            signal_timeout_minutes=config.DEFAULT_SIGNAL_TIMEOUT_MINUTES,
            min_rr_ratio=config.DEFAULT_MIN_RR_RATIO,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def update_user_keys(telegram_id: int, api_key: str, api_secret: str) -> None:
    from utils.crypto import encrypt
    with Session(engine) as session:
        session.execute(
            update(User).where(User.telegram_id == telegram_id).values(
                binance_api_key_enc=encrypt(api_key),
                binance_api_secret_enc=encrypt(api_secret),
            )
        )
        session.commit()


def update_user_setting(telegram_id: int, **kwargs) -> None:
    allowed = {
        "fixed_position_usdt", "sl_percent", "tp_percent", "leverage", "timeframe",
        "last_market_analysis_at",
        "max_open_positions", "min_confidence", "signal_timeout_minutes", "min_rr_ratio",
    }
    values = {k: v for k, v in kwargs.items() if k in allowed}
    if not values:
        return
    with Session(engine) as session:
        session.execute(update(User).where(User.telegram_id == telegram_id).values(**values))
        session.commit()


def touch_user_last_analysis(telegram_id: int) -> None:
    """Обновить время последнего цикла анализа для пользователя."""
    update_user_setting(telegram_id, last_market_analysis_at=datetime.utcnow())


def is_whitelisted(telegram_id: int) -> bool:
    return telegram_id in config.TELEGRAM_WHITELIST


# ── Signals ───────────────────────────────────────────────────────────────────

def save_signal(signal: Signal) -> Signal:
    with Session(engine) as session:
        session.add(signal)
        session.commit()
        session.refresh(signal)
        stats = session.scalar(select(Statistics))
        if stats:
            stats.total_signals += 1
            session.commit()
            session.refresh(signal)
        session.expunge(signal)
        return signal


def get_signal(signal_id: int) -> Optional[Signal]:
    with Session(engine) as session:
        return session.get(Signal, signal_id)


def get_pending_signals() -> list[Signal]:
    with Session(engine) as session:
        return list(session.scalars(
            select(Signal).where(Signal.status == SignalStatus.PENDING)
        ).all())


def update_signal_status(
    signal_id: int, status: SignalStatus, telegram_message_id: Optional[int] = None
) -> None:
    with Session(engine) as session:
        values = {"status": status}
        if telegram_message_id is not None:
            values["telegram_message_id"] = telegram_message_id
        session.execute(update(Signal).where(Signal.id == signal_id).values(**values))
        session.commit()


# ── Trades ────────────────────────────────────────────────────────────────────

def save_trade(trade: Trade) -> Trade:
    with Session(engine) as session:
        session.add(trade)
        session.commit()
        session.refresh(trade)
        return trade


def get_open_trades(user_id: int = None) -> list[Trade]:
    with Session(engine) as session:
        q = select(Trade).where(Trade.status == TradeStatus.OPEN)
        if user_id is not None:
            q = q.where(Trade.user_id == user_id)
        return list(session.scalars(q).all())


def get_trade_by_signal(signal_id: int) -> Optional[Trade]:
    with Session(engine) as session:
        return session.scalar(select(Trade).where(Trade.signal_id == signal_id))


def get_recent_signals(user_id: int, limit: int = 20) -> list[Signal]:
    """Последние сигналы пользователя (со связанными сделками)."""
    with Session(engine) as session:
        from sqlalchemy.orm import joinedload
        return list(session.scalars(
            select(Signal)
            .where(Signal.user_id == user_id)
            .options(joinedload(Signal.trade))
            .order_by(Signal.created_at.desc())
            .limit(limit)
        ).all())


def close_trade(
    trade_id: int, exit_price: float, status: TradeStatus, pnl_usdt: float, pnl_percent: float
) -> None:
    with Session(engine) as session:
        session.execute(
            update(Trade).where(Trade.id == trade_id).values(
                exit_price=exit_price,
                status=status,
                pnl_usdt=pnl_usdt,
                pnl_percent=pnl_percent,
                closed_at=datetime.utcnow(),
            )
        )
        session.commit()
    _update_statistics(pnl_usdt, status)


# ── Statistics ────────────────────────────────────────────────────────────────

def get_statistics() -> Statistics:
    with Session(engine) as session:
        return session.scalar(select(Statistics))


def _update_statistics(pnl_usdt: float, status: TradeStatus) -> None:
    with Session(engine) as session:
        stats = session.scalar(select(Statistics))
        stats.total_trades += 1
        if status == TradeStatus.CLOSED_TP:
            stats.winning_trades += 1
        else:
            stats.losing_trades += 1
        stats.total_pnl_usdt += pnl_usdt
        if stats.total_trades > 0:
            stats.win_rate = stats.winning_trades / stats.total_trades
        if pnl_usdt > stats.best_trade_pnl:
            stats.best_trade_pnl = pnl_usdt
        if pnl_usdt < stats.worst_trade_pnl:
            stats.worst_trade_pnl = pnl_usdt
        session.commit()
