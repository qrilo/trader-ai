from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Enum,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SignalDirection(PyEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class SignalStatus(PyEnum):
    PENDING = "PENDING"       # ждёт апрува
    APPROVED = "APPROVED"     # апрувнут пользователем
    REJECTED = "REJECTED"     # отклонён пользователем
    EXPIRED = "EXPIRED"       # истёк таймаут
    CANCELLED = "CANCELLED"   # отменён системой


class TradeStatus(PyEnum):
    OPEN = "OPEN"
    CLOSED_TP = "CLOSED_TP"   # закрыта по Take Profit
    CLOSED_SL = "CLOSED_SL"   # закрыта по Stop Loss
    CLOSED_MANUAL = "CLOSED_MANUAL"  # закрыта вручную


class Signal(Base):
    """Торговый сигнал сгенерированный системой."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection), nullable=False)
    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus), default=SignalStatus.PENDING, nullable=False
    )

    # Цены
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)

    # Риск-менеджмент
    position_size_usdt: Mapped[float] = mapped_column(Float, nullable=False)
    risk_reward_ratio: Mapped[float] = mapped_column(Float, nullable=False)

    # ML-метрики
    ml_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)

    # Индикаторы на момент сигнала (для анализа)
    rsi: Mapped[float] = mapped_column(Float, nullable=True)
    macd: Mapped[float] = mapped_column(Float, nullable=True)
    volume_change: Mapped[float] = mapped_column(Float, nullable=True)

    # Telegram message id для обновления карточки
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    trade: Mapped["Trade"] = relationship("Trade", back_populates="signal", uselist=False)


class Trade(Base):
    """Реальная сделка исполненная на бирже."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection), nullable=False)
    status: Mapped[TradeStatus] = mapped_column(
        Enum(TradeStatus), default=TradeStatus.OPEN, nullable=False
    )

    # Цены исполнения
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)

    # Размер позиции
    position_size_usdt: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    # ID ордеров на бирже
    exchange_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    exchange_sl_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    exchange_tp_order_id: Mapped[str] = mapped_column(String(100), nullable=True)

    # Результат
    pnl_usdt: Mapped[float] = mapped_column(Float, nullable=True)
    pnl_percent: Mapped[float] = mapped_column(Float, nullable=True)

    signal: Mapped["Signal"] = relationship("Signal", back_populates="trade")


class Statistics(Base):
    """Агрегированная статистика для быстрого отображения."""

    __tablename__ = "statistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    total_signals: Mapped[int] = mapped_column(Integer, default=0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)

    total_pnl_usdt: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)

    best_trade_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    worst_trade_pnl: Mapped[float] = mapped_column(Float, default=0.0)
