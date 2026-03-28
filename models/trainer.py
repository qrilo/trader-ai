from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from config import config
from data.collector import fetch_historical_candles
from data.indicators import add_indicators, add_price_ratios, get_feature_columns


MODELS_DIR = Path(__file__).parent / "saved"
MODELS_DIR.mkdir(exist_ok=True)


def _model_key(symbol: str, timeframe: str) -> str:
    """Уникальный ключ для файлов модели: BTC_USDT_15m"""
    return f"{symbol.replace('/', '_')}_{timeframe}"


def _prepare_dataset(df: pd.DataFrame, future_periods: int = 4) -> tuple[pd.DataFrame, pd.Series]:
    """
    Подготовить датасет для обучения.
    Целевая переменная: выросла ли цена через future_periods свечей минимум на 1%.
    """
    df = df.copy()

    future_return = df["close"].shift(-future_periods) / df["close"] - 1
    df["target"] = (future_return > 0.01).astype(int)

    df.dropna(inplace=True)

    features = get_feature_columns()
    available = [f for f in features if f in df.columns]
    X = df[available]
    y = df["target"]

    return X, y


def _step(n: int, total: int, text: str) -> None:
    logger.info(f"[{n}/{total}] {text}")


def train(symbol: str, timeframe: str = None) -> None:
    """Обучить XGBoost модель для символа+таймфрейма и сохранить на диск."""
    timeframe = timeframe or config.TIMEFRAME
    key = _model_key(symbol, timeframe)
    STEPS = 6

    logger.info(f"")
    logger.info(f"{'='*50}")
    logger.info(f"  Обучение модели: {symbol} [{timeframe}]")
    logger.info(f"{'='*50}")

    _step(1, STEPS, f"Загрузка исторических данных за {config.TRAINING_YEARS} года...")
    logger.info(f"  (это может занять 1-2 минуты, идёт скачивание с Binance)")
    df = fetch_historical_candles(symbol, timeframe=timeframe, years=config.TRAINING_YEARS)
    logger.info(f"  Загружено свечей: {len(df):,}")
    if len(df) < 100:
        raise ValueError(
            f"Слишком мало свечей ({len(df)}) для {symbol} [{timeframe}] — "
            "проверь, что интервал поддерживается Binance (см. config.SUPPORTED_TIMEFRAMES)."
        )

    _step(2, STEPS, "Расчёт технических индикаторов (RSI, MACD, Bollinger...)")
    df = add_indicators(df)
    df = add_price_ratios(df)
    logger.info(f"  Индикаторов рассчитано: {len(df.columns)}")

    _step(3, STEPS, "Подготовка датасета для обучения...")
    X, y = _prepare_dataset(df)
    logger.info(f"  Примеров в датасете: {len(X):,}")
    logger.info(f"  Прибыльных сигналов: {y.mean():.1%}")

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    _step(4, STEPS, "Кросс-валидация модели (5 фолдов, не зависло — просто считает)...")
    tscv = TimeSeriesSplit(n_splits=5)
    val_scores = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X_scaled)):
        X_train, X_val = X_scaled[train_idx], X_scaled[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        model = XGBClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        score = model.score(X_val, y_val)
        val_scores.append(score)
        logger.info(f"  Фолд {fold + 1}/5 — точность: {score:.1%}")

    avg_score = np.mean(val_scores)
    logger.info(f"  Средняя точность: {avg_score:.1%}")

    _step(5, STEPS, "Финальное обучение на полном датасете...")
    logger.info(f"  (самый долгий шаг, ~1-3 минуты)")
    final_model = XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
    )
    final_model.fit(X_scaled, y, verbose=False)

    _step(6, STEPS, "Сохранение модели на диск...")
    joblib.dump(final_model, MODELS_DIR / f"{key}_model.pkl")
    joblib.dump(scaler, MODELS_DIR / f"{key}_scaler.pkl")
    joblib.dump(list(X.columns), MODELS_DIR / f"{key}_features.pkl")

    logger.info(f"")
    logger.info(f"  ✅ {symbol} [{timeframe}] готово! Точность модели: {avg_score:.1%}")
    logger.info(f"{'='*50}")


def needs_training(symbol: str, timeframe: str = None) -> bool:
    """Проверить нужно ли обучать модель для символа и таймфрейма."""
    timeframe = timeframe or config.TIMEFRAME
    key = _model_key(symbol, timeframe)
    model_path = MODELS_DIR / f"{key}_model.pkl"

    if not model_path.exists():
        logger.info(f"  {symbol} [{timeframe}]: модель не найдена → нужно обучить")
        return True

    age_days = (datetime.now().timestamp() - model_path.stat().st_mtime) / 86400
    if age_days > 30:
        logger.info(f"  {symbol} [{timeframe}]: модель устарела ({age_days:.0f} дней) → переобучаем")
        return True

    logger.info(f"  {symbol} [{timeframe}]: модель актуальна ({age_days:.0f} дней) → пропускаем")
    return False


def model_exists(symbol: str, timeframe: str = None) -> bool:
    """Проверить существует ли модель для символа и таймфрейма."""
    timeframe = timeframe or config.TIMEFRAME
    key = _model_key(symbol, timeframe)
    return (MODELS_DIR / f"{key}_model.pkl").exists()


def train_all(force: bool = False, timeframe: str = None) -> None:
    """
    Обучить модели для всех символов и всех таймфреймов.
    force=True — переобучить даже если модели актуальны.
    timeframe — если указан, обучить только этот таймфрейм.
    """
    symbols = config.TRADING_SYMBOLS
    timeframes = [timeframe] if timeframe else list(config.SUPPORTED_TIMEFRAMES.keys())

    total_combos = len(symbols) * len(timeframes)
    logger.info(f"")
    logger.info(f"🚀 Запуск обучения моделей")
    logger.info(f"Символы:    {', '.join(symbols)}")
    logger.info(f"Таймфреймы: {', '.join(timeframes)}")
    logger.info(f"История:    {config.TRAINING_YEARS} года")
    if not force:
        logger.info(f"Режим: умный (пропускаем актуальные модели)")
    else:
        logger.info(f"Режим: принудительное переобучение")
    logger.info(f"Всего комбинаций: {total_combos}")
    logger.info(f"Примерное время:  {total_combos * 5}-{total_combos * 15} минут")
    logger.info(f"")

    success = []
    failed = []
    n = 0

    for tf in timeframes:
        for symbol in symbols:
            n += 1
            label = f"{symbol} [{tf}]"
            logger.info(f"--- [{n}/{total_combos}] {label} ---")
            if not force and not needs_training(symbol, tf):
                success.append(label)
                continue
            try:
                train(symbol, tf)
                success.append(label)
            except Exception as e:
                logger.error(f"❌ Ошибка обучения {label}: {e}")
                failed.append(label)

    logger.info(f"")
    logger.info(f"{'='*50}")
    logger.info(f"  Обучение завершено!")
    logger.info(f"  ✅ Успешно ({len(success)}): {', '.join(success) if success else 'нет'}")
    if failed:
        logger.info(f"  ❌ Ошибки  ({len(failed)}): {', '.join(failed)}")
    logger.info(f"  Модели сохранены в: {MODELS_DIR}")
    logger.info(f"{'='*50}")
    logger.info(f"")
