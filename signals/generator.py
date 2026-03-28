from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from config import config
from data.collector import fetch_candles, get_account_balance
from data.indicators import add_indicators, add_price_ratios
from database import repository
from database.models import Signal, SignalDirection, SignalStatus
from models.predictor import get_predictor
from models.sentiment import analyze_sentiment
from signals.risk import calculate_risk_params


@dataclass
class SignalCandidate:
    symbol: str
    direction: str
    confidence: float
    entry_price: float
    atr: float
    rsi: float
    macd: float
    volume_ratio: float
    sentiment_score: float
    reason: str


def _detect_direction(df, confidence: float) -> Optional[str]:
    """
    Определить направление сделки на основе индикаторов.
    Возвращает LONG, SHORT или None если нет чёткого сигнала.
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]

    rsi = last["rsi"]
    macd_hist = last["macd_hist"]
    prev_macd_hist = prev["macd_hist"]
    price_vs_ema200 = last.get("price_vs_ema200", 0)
    volume_ratio = last["volume_ratio"]

    long_score = 0
    short_score = 0

    # RSI: перепроданность → LONG, перекупленность → SHORT
    if rsi < 35:
        long_score += 2
    elif rsi < 45:
        long_score += 1
    elif rsi > 65:
        short_score += 2
    elif rsi > 55:
        short_score += 1

    # MACD пересечение
    if macd_hist > 0 and prev_macd_hist <= 0:
        long_score += 2
    elif macd_hist > 0:
        long_score += 1
    elif macd_hist < 0 and prev_macd_hist >= 0:
        short_score += 2
    elif macd_hist < 0:
        short_score += 1

    # Цена относительно EMA200 (глобальный тренд)
    if price_vs_ema200 > 0.02:
        long_score += 1
    elif price_vs_ema200 < -0.02:
        short_score += 1

    # Подтверждение объёмом
    if volume_ratio > 1.3:
        if long_score > short_score:
            long_score += 1
        elif short_score > long_score:
            short_score += 1

    # ML уверенность корректирует направление
    if confidence > 0.65:
        long_score += 1
    elif confidence < 0.35:
        short_score += 1

    if long_score > short_score and long_score >= 3:
        return "LONG"
    elif short_score > long_score and short_score >= 3:
        return "SHORT"
    return None


def _build_reason(last_row, direction: str, sentiment_score: float) -> str:
    """Сформировать текстовое объяснение сигнала."""
    reasons = []

    rsi = last_row["rsi"]
    macd_hist = last_row["macd_hist"]
    volume_ratio = last_row["volume_ratio"]

    if direction == "LONG":
        if rsi < 35:
            reasons.append(f"RSI={rsi:.0f} (перепроданность)")
        if macd_hist > 0:
            reasons.append("MACD бычье пересечение")
    else:
        if rsi > 65:
            reasons.append(f"RSI={rsi:.0f} (перекупленность)")
        if macd_hist < 0:
            reasons.append("MACD медвежье пересечение")

    if volume_ratio > 1.3:
        reasons.append(f"объём +{(volume_ratio - 1) * 100:.0f}% от среднего")

    if sentiment_score > 0.3:
        reasons.append("позитивный новостной фон")
    elif sentiment_score < -0.3:
        reasons.append("негативный новостной фон")

    return ", ".join(reasons) if reasons else "технический сигнал"


def generate_signal(symbol: str) -> Optional[Signal]:
    """
    Главная функция: анализирует символ и возвращает Signal если есть возможность,
    или None если условия не выполнены.
    """
    logger.info(f"Анализ {symbol}...")

    try:
        # Загружаем свежие свечи
        df = fetch_candles(symbol)
        df = add_indicators(df)
        df = add_price_ratios(df)

        # ML-предсказание
        predictor = get_predictor(symbol)
        confidence = predictor.predict(df)
        if confidence is None:
            return None

        last = df.iloc[-1]
        entry_price = float(last["close"])
        atr = float(last["atr"])

        # Определяем направление
        direction = _detect_direction(df, confidence)
        if direction is None:
            logger.debug(f"{symbol}: нет чёткого направления")
            return None

        # Проверяем порог уверенности ML
        effective_confidence = confidence if direction == "LONG" else (1 - confidence)
        if effective_confidence < config.MIN_CONFIDENCE:
            logger.debug(f"{symbol}: уверенность {effective_confidence:.2f} < {config.MIN_CONFIDENCE}")
            return None

        # Анализ сентимента новостей
        sentiment = analyze_sentiment(symbol)

        # Формируем сигнал
        reason = _build_reason(last, direction, sentiment.score)

        # Проверяем количество открытых позиций
        open_trades = repository.get_open_trades()
        if len(open_trades) >= config.MAX_OPEN_POSITIONS:
            logger.info(f"Достигнут лимит открытых позиций ({config.MAX_OPEN_POSITIONS})")
            return None

        # Получаем баланс для расчёта размера позиции
        balance = get_account_balance()
        if balance < 10:
            logger.warning("Недостаточно средств на балансе")
            return None

        # Рассчитываем риск-параметры
        risk = calculate_risk_params(direction, entry_price, atr, balance)

        # Проверяем R/R
        if risk.risk_reward_ratio < config.MIN_RR_RATIO:
            logger.debug(f"{symbol}: R/R={risk.risk_reward_ratio:.2f} < {config.MIN_RR_RATIO}")
            return None

        # Создаём сигнал
        signal = Signal(
            symbol=symbol,
            direction=SignalDirection[direction],
            status=SignalStatus.PENDING,
            entry_price=risk.entry_price,
            stop_loss=risk.stop_loss,
            take_profit=risk.take_profit,
            position_size_usdt=risk.position_size_usdt,
            risk_reward_ratio=risk.risk_reward_ratio,
            ml_confidence=round(effective_confidence, 3),
            sentiment_score=round(sentiment.score, 3),
            rsi=round(float(last["rsi"]), 2),
            macd=round(float(last["macd"]), 4),
            volume_change=round(float(last["volume_ratio"]) - 1, 3),
            expires_at=datetime.utcnow() + timedelta(minutes=config.SIGNAL_TIMEOUT_MINUTES),
        )

        saved_signal = repository.save_signal(signal)
        logger.info(
            f"Сигнал сгенерирован: {symbol} {direction} "
            f"уверенность={effective_confidence:.0%} R/R={risk.risk_reward_ratio}"
        )
        return saved_signal

    except FileNotFoundError:
        logger.warning(f"Модель для {symbol} не обучена, пропускаем")
        return None
    except Exception as e:
        logger.error(f"Ошибка генерации сигнала {symbol}: {e}")
        return None


def expire_old_signals() -> None:
    """Отмечаем просроченные сигналы которые не были апрувнуты."""
    pending = repository.get_pending_signals()
    now = datetime.utcnow()
    for signal in pending:
        if signal.expires_at < now:
            repository.update_signal_status(signal.id, SignalStatus.EXPIRED)
            logger.debug(f"Сигнал #{signal.id} {signal.symbol} истёк")
