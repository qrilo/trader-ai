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


def _prepare_dataset(df: pd.DataFrame, future_periods: int = 4) -> tuple[pd.DataFrame, pd.Series]:
    """
    Подготовить датасет для обучения.
    Целевая переменная: выросла ли цена через future_periods свечей минимум на 1%.
    """
    df = df.copy()

    # Целевая переменная: 1 = цена выросла на 1%+, 0 = нет
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


def train(symbol: str) -> None:
    """Обучить XGBoost модель для символа и сохранить на диск."""
    STEPS = 6
    logger.info(f"")
    logger.info(f"{'='*50}")
    logger.info(f"  Обучение модели: {symbol}")
    logger.info(f"{'='*50}")

    _step(1, STEPS, f"Загрузка исторических данных за {config.TRAINING_YEARS} года...")
    logger.info(f"  (это может занять 1-2 минуты, идёт скачивание с Binance)")
    df = fetch_historical_candles(symbol, timeframe=config.TIMEFRAME, years=config.TRAINING_YEARS)
    logger.info(f"  Загружено свечей: {len(df):,}")

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
    symbol_key = symbol.replace("/", "_")
    joblib.dump(final_model, MODELS_DIR / f"{symbol_key}_model.pkl")
    joblib.dump(scaler, MODELS_DIR / f"{symbol_key}_scaler.pkl")
    joblib.dump(list(X.columns), MODELS_DIR / f"{symbol_key}_features.pkl")

    logger.info(f"")
    logger.info(f"  ✅ {symbol} готово! Точность модели: {avg_score:.1%}")
    logger.info(f"{'='*50}")


def train_all() -> None:
    """Обучить модели для всех символов из конфига."""
    symbols = config.TRADING_SYMBOLS
    logger.info(f"")
    logger.info(f"🚀 Запуск обучения моделей")
    logger.info(f"Символы: {', '.join(symbols)}")
    logger.info(f"Таймфрейм: {config.TIMEFRAME}")
    logger.info(f"История: {config.TRAINING_YEARS} года")
    logger.info(f"Примерное время: {len(symbols) * 5}-{len(symbols) * 15} минут")
    logger.info(f"")

    success = []
    failed = []

    for i, symbol in enumerate(symbols, 1):
        logger.info(f"Символ {i}/{len(symbols)}: {symbol}")
        try:
            train(symbol)
            success.append(symbol)
        except Exception as e:
            logger.error(f"❌ Ошибка обучения {symbol}: {e}")
            failed.append(symbol)

    logger.info(f"")
    logger.info(f"{'='*50}")
    logger.info(f"  Обучение завершено!")
    logger.info(f"  ✅ Успешно: {', '.join(success) if success else 'нет'}")
    if failed:
        logger.info(f"  ❌ Ошибки:  {', '.join(failed)}")
    logger.info(f"  Модели сохранены в: {MODELS_DIR}")
    logger.info(f"{'='*50}")
    logger.info(f"")
