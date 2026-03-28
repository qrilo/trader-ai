from datetime import datetime
from typing import Optional
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
    CLOSED_TP = "CLOSED_TP"
    CLOSED_SL = "CLOSED_SL"
    CLOSED_MANUAL = "CLOSED_MANUAL"


class User(Base):
    """Пользователь бота."""

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Таймфрейм анализа (свой у каждого пользователя)
    timeframe: Mapped[str] = mapped_column(String(5), default="15m")
    last_market_analysis_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Binance API ключи (зашифрованы через utils/crypto.py)
    binance_api_key_enc: Mapped[str] = mapped_column(Text, nullable=True)
    binance_api_secret_enc: Mapped[str] = mapped_column(Text, nullable=True)

    # Индивидуальные торговые настройки (маржа USDT, SL/TP в % от цены входа)
    fixed_position_usdt: Mapped[float] = mapped_column(Float, default=50.0)
    sl_percent: Mapped[float] = mapped_column(Float, default=1.5)
    tp_percent: Mapped[float] = mapped_column(Float, default=3.0)
    leverage: Mapped[int] = mapped_column(Integer, default=5)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=3)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.65)
    signal_timeout_minutes: Mapped[int] = mapped_column(Integer, default=10)
    min_rr_ratio: Mapped[float] = mapped_column(Float, default=2.0)

    signals: Mapped[list["Signal"]] = relationship("Signal", back_populates="user")
    trades: Mapped[list["Trade"]] = relationship("Trade", back_populates="user")

    @property
    def has_api_keys(self) -> bool:
        return bool(self.binance_api_key_enc and self.binance_api_secret_enc)

    def get_api_key(self) -> str:
        from utils.crypto import decrypt
        return decrypt(self.binance_api_key_enc) if self.binance_api_key_enc else ""

    def get_api_secret(self) -> str:
        from utils.crypto import decrypt
        return decrypt(self.binance_api_secret_enc) if self.binance_api_secret_enc else ""


class Settings(Base):
    """Глобальные настройки бота (key-value)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Signal(Base):
    """Торговый сигнал сгенерированный системой для конкретного пользователя."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=True)
    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection), nullable=False)
    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus), default=SignalStatus.PENDING, nullable=False
    )

    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    position_size_usdt: Mapped[float] = mapped_column(Float, nullable=False)
    risk_reward_ratio: Mapped[float] = mapped_column(Float, nullable=False)

    ml_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)

    rsi: Mapped[float] = mapped_column(Float, nullable=True)
    macd: Mapped[float] = mapped_column(Float, nullable=True)
    volume_change: Mapped[float] = mapped_column(Float, nullable=True)

    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="signals")
    trade: Mapped["Trade"] = relationship("Trade", back_populates="signal", uselist=False)


class Trade(Base):
    """Реальная сделка исполненная на бирже."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection), nullable=False)
    status: Mapped[TradeStatus] = mapped_column(
        Enum(TradeStatus), default=TradeStatus.OPEN, nullable=False
    )

    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    position_size_usdt: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    exchange_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    exchange_sl_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    exchange_tp_order_id: Mapped[str] = mapped_column(String(100), nullable=True)

    pnl_usdt: Mapped[float] = mapped_column(Float, nullable=True)
    pnl_percent: Mapped[float] = mapped_column(Float, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="trades")
    signal: Mapped["Signal"] = relationship("Signal", back_populates="trade")


class Statistics(Base):
    """Агрегированная статистика."""

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
