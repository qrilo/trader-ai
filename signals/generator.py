from datetime import datetime, timedelta
from typing import Optional, Tuple

from loguru import logger

from config import config
from data.collector import fetch_candles
from data.indicators import add_indicators, add_price_ratios
from database import repository
from database.models import Signal, SignalDirection, SignalStatus, User
from models.predictor import get_predictor
from models.sentiment import analyze_sentiment
from signals.risk import calculate_risk_params


def _log_signal_skip(symbol: str, user_id: int, reason: str) -> None:
    msg = f"{symbol} (user={user_id}): пропуск — {reason}"
    if config.VERBOSE_SIGNAL_ANALYSIS:
        logger.info(msg)
    else:
        logger.debug(msg)


def _log_analyze_start(symbol: str, user_id: int) -> None:
    msg = f"Анализ {symbol} (user={user_id})..."
    if config.VERBOSE_SIGNAL_ANALYSIS:
        logger.info(msg)
    else:
        logger.debug(msg)


def _detect_direction(df, confidence: float) -> Optional[str]:
    last = df.iloc[-1]
    prev = df.iloc[-2]

    rsi = last["rsi"]
    macd_hist = last["macd_hist"]
    prev_macd_hist = prev["macd_hist"]
    price_vs_ema200 = last.get("price_vs_ema200", 0)
    volume_ratio = last["volume_ratio"]

    long_score = 0
    short_score = 0

    if rsi < 35:
        long_score += 2
    elif rsi < 45:
        long_score += 1
    elif rsi > 65:
        short_score += 2
    elif rsi > 55:
        short_score += 1

    if macd_hist > 0 and prev_macd_hist <= 0:
        long_score += 2
    elif macd_hist > 0:
        long_score += 1
    elif macd_hist < 0 and prev_macd_hist >= 0:
        short_score += 2
    elif macd_hist < 0:
        short_score += 1

    if price_vs_ema200 > 0.02:
        long_score += 1
    elif price_vs_ema200 < -0.02:
        short_score += 1

    if volume_ratio > 1.3:
        if long_score > short_score:
            long_score += 1
        elif short_score > long_score:
            short_score += 1

    if confidence > 0.65:
        long_score += 1
    elif confidence < 0.35:
        short_score += 1

    if long_score > short_score and long_score >= 3:
        return "LONG"
    elif short_score > long_score and short_score >= 3:
        return "SHORT"
    return None


def _build_trigger_reason(
    last_row,
    direction: str,
    sentiment_score: float,
    effective_confidence: float,
    timeframe: str,
    min_confidence: float,
    sl_pct: float,
    tp_pct: float,
    rr: float,
) -> str:
    """Краткое объяснение для Telegram: почему сработал триггер."""
    rsi = float(last_row["rsi"])
    macd_hist = float(last_row["macd_hist"])
    vol_r = float(last_row["volume_ratio"])
    p_ema = float(last_row.get("price_vs_ema200", 0) or 0)

    lines = [
        f"таймфрейм <b>{timeframe}</b>, направление <b>{direction}</b>",
        f"ML: уверенность <b>{effective_confidence:.0%}</b> (мин. порог {min_confidence:.0%})",
        f"RSI <b>{rsi:.0f}</b>, MACD hist {macd_hist:+.4f}",
    ]
    if vol_r > 1.3:
        lines.append(f"объём выше среднего (×{vol_r:.2f})")
    if abs(p_ema) > 0.02:
        lines.append(
            "цена " + ("выше" if p_ema > 0 else "ниже") + f" EMA200 ({p_ema:+.1%})"
        )
    if sentiment_score > 0.2:
        lines.append("новости: позитивный фон (FinBERT)")
    elif sentiment_score < -0.2:
        lines.append("новости: негативный фон (FinBERT)")
    else:
        lines.append("новости: нейтрально")

    lines.append(f"риск: SL {sl_pct:.1f}% / TP {tp_pct:.1f}% → R/R <b>1:{rr:.1f}</b>")

    return "\n".join(f"• {line}" for line in lines)


def _get_account_balance(user: User) -> float:
    """Получить баланс конкретного пользователя."""
    from trading.exchange import get_exchange_for_user
    exchange = get_exchange_for_user(user)
    exchange.load_time_difference()
    balance = exchange.fetch_balance()
    return float(balance.get("USDT", {}).get("free", 0.0))


def generate_signal(symbol: str, user: User) -> Optional[Tuple[Signal, str]]:
    """Анализирует символ. Возвращает (Signal, текст «почему сработало») или None."""
    _log_analyze_start(symbol, user.telegram_id)

    min_confidence = user.min_confidence
    max_open_positions = user.max_open_positions
    signal_timeout = user.signal_timeout_minutes
    min_rr = user.min_rr_ratio
    user_id = user.telegram_id

    try:
        timeframe = getattr(user, "timeframe", None) or config.TIMEFRAME
        df = fetch_candles(symbol, timeframe=timeframe)
        df = add_indicators(df)
        df = add_price_ratios(df)

        predictor = get_predictor(symbol, timeframe)
        confidence = predictor.predict(df)
        if confidence is None:
            _log_signal_skip(symbol, user_id, "ML: нет предсказания (модель вернула None)")
            return None

        last = df.iloc[-1]
        entry_price = float(last["close"])

        direction = _detect_direction(df, confidence)
        if direction is None:
            _log_signal_skip(
                symbol,
                user_id,
                "направление: нет устойчивого LONG/SHORT (порог по индикаторам не набран)",
            )
            return None

        effective_confidence = confidence if direction == "LONG" else (1 - confidence)
        if effective_confidence < min_confidence:
            _log_signal_skip(
                symbol,
                user_id,
                f"ML: уверенность {effective_confidence:.2f} < порога {min_confidence} ({direction})",
            )
            return None

        sentiment = analyze_sentiment(symbol, user=user)

        open_trades = repository.get_open_trades(user_id=user_id)
        if len(open_trades) >= max_open_positions:
            _log_signal_skip(
                symbol,
                user_id,
                f"лимит позиций: открыто {len(open_trades)}/{max_open_positions}",
            )
            return None

        balance = _get_account_balance(user)

        margin_usdt = float(getattr(user, "fixed_position_usdt", 0) or 0)
        if margin_usdt <= 0:
            margin_usdt = config.DEFAULT_MARGIN_USDT
        sl_pct = float(getattr(user, "sl_percent", 0) or 0) or config.DEFAULT_SL_PERCENT
        tp_pct = float(getattr(user, "tp_percent", 0) or 0) or config.DEFAULT_TP_PERCENT

        if balance < margin_usdt:
            logger.warning(
                f"Недостаточно USDT: нужно маржу {margin_usdt}, на балансе {balance:.2f}"
            )
            return None

        risk = calculate_risk_params(
            direction, entry_price, margin_usdt, sl_pct, tp_pct,
        )

        if risk.risk_reward_ratio < min_rr:
            _log_signal_skip(
                symbol,
                user_id,
                f"R/R={risk.risk_reward_ratio:.2f} < min_rr={min_rr} "
                f"(SL {sl_pct:.1f}% / TP {tp_pct:.1f}%)",
            )
            return None

        signal = Signal(
            user_id=user_id,
            symbol=symbol,
            timeframe=timeframe,
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
            expires_at=datetime.utcnow() + timedelta(minutes=signal_timeout),
        )

        saved_signal = repository.save_signal(signal)
        trigger_reason = _build_trigger_reason(
            last,
            direction,
            sentiment.score,
            effective_confidence,
            timeframe,
            min_confidence,
            sl_pct,
            tp_pct,
            risk.risk_reward_ratio,
        )
        logger.info(
            f"Сигнал #{saved_signal.id}: {symbol} {direction} "
            f"уверенность={effective_confidence:.0%} R/R={risk.risk_reward_ratio}"
        )
        return saved_signal, trigger_reason

    except FileNotFoundError:
        logger.warning(
            f"{symbol} (user={user.telegram_id}): модель не обучена — нужно переобучение (trainer)"
        )
        return None
    except Exception as e:
        logger.error(f"Ошибка генерации сигнала {symbol}: {e}")
        return None


def expire_old_signals() -> None:
    pending = repository.get_pending_signals()
    now = datetime.utcnow()
    for signal in pending:
        if signal.expires_at < now:
            repository.update_signal_status(signal.id, SignalStatus.EXPIRED)
            logger.debug(f"Сигнал #{signal.id} {signal.symbol} истёк")
