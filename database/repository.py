from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from config import config
from database.models import Base, Signal, SignalStatus, Statistics, Trade, TradeStatus


engine = create_engine(config.DATABASE_URL)


def init_db() -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        stats = session.scalar(select(Statistics))
        if not stats:
            session.add(Statistics())
            session.commit()


def save_signal(signal: Signal) -> Signal:
    with Session(engine) as session:
        session.add(signal)
        session.commit()
        session.refresh(signal)
        return signal


def get_signal(signal_id: int) -> Optional[Signal]:
    with Session(engine) as session:
        return session.get(Signal, signal_id)


def get_pending_signals() -> list[Signal]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(Signal).where(Signal.status == SignalStatus.PENDING)
            ).all()
        )


def update_signal_status(signal_id: int, status: SignalStatus, telegram_message_id: Optional[int] = None) -> None:
    with Session(engine) as session:
        values = {"status": status}
        if telegram_message_id is not None:
            values["telegram_message_id"] = telegram_message_id
        session.execute(update(Signal).where(Signal.id == signal_id).values(**values))
        session.commit()


def save_trade(trade: Trade) -> Trade:
    with Session(engine) as session:
        session.add(trade)
        session.commit()
        session.refresh(trade)
        return trade


def get_open_trades() -> list[Trade]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(Trade).where(Trade.status == TradeStatus.OPEN)
            ).all()
        )


def get_trade_by_signal(signal_id: int) -> Optional[Trade]:
    with Session(engine) as session:
        return session.scalar(select(Trade).where(Trade.signal_id == signal_id))


def close_trade(trade_id: int, exit_price: float, status: TradeStatus, pnl_usdt: float, pnl_percent: float) -> None:
    with Session(engine) as session:
        session.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(
                exit_price=exit_price,
                status=status,
                pnl_usdt=pnl_usdt,
                pnl_percent=pnl_percent,
                closed_at=datetime.utcnow(),
            )
        )
        session.commit()
    _update_statistics(pnl_usdt, status)


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
