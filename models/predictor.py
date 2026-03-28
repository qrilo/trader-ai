from pathlib import Path
from typing import Optional

import joblib
import pandas as pd
from loguru import logger

from config import config
from data.indicators import add_indicators, add_price_ratios


MODELS_DIR = Path(__file__).parent / "saved"


class Predictor:
    """Загружает обученную модель и делает предсказания."""

    def __init__(self, symbol: str, timeframe: str = None):
        self.symbol = symbol
        self.timeframe = timeframe or config.TIMEFRAME
        self._key = f"{symbol.replace('/', '_')}_{self.timeframe}"
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self._load()

    def _load(self) -> None:
        model_path = MODELS_DIR / f"{self._key}_model.pkl"
        scaler_path = MODELS_DIR / f"{self._key}_scaler.pkl"
        features_path = MODELS_DIR / f"{self._key}_features.pkl"

        if not model_path.exists():
            raise FileNotFoundError(
                f"Модель для {self.symbol} [{self.timeframe}] не найдена. "
                f"Запустите обучение через бота: ⚙️ Настройки → 🔄 Переобучить"
            )

        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path)
        self.feature_columns = joblib.load(features_path)
        logger.debug(f"Модель {self.symbol} [{self.timeframe}] загружена")

    def predict(self, df: pd.DataFrame) -> Optional[float]:
        """
        Предсказать вероятность роста цены.
        Возвращает float от 0 до 1 (вероятность роста).
        """
        try:
            df = add_indicators(df)
            df = add_price_ratios(df)

            available = [f for f in self.feature_columns if f in df.columns]
            last_row = df[available].iloc[[-1]]

            X_scaled = self.scaler.transform(last_row)
            proba = self.model.predict_proba(X_scaled)[0][1]

            logger.debug(f"{self.symbol} [{self.timeframe}]: вероятность роста {proba:.3f}")
            return float(proba)

        except Exception as e:
            logger.error(f"Ошибка предсказания {self.symbol}: {e}")
            return None

    def is_model_available(self) -> bool:
        return (MODELS_DIR / f"{self._key}_model.pkl").exists()


_predictors: dict[str, Predictor] = {}


def get_predictor(symbol: str, timeframe: str = None) -> Predictor:
    """Кешированный доступ к предиктору."""
    timeframe = timeframe or config.TIMEFRAME
    cache_key = f"{symbol}_{timeframe}"
    if cache_key not in _predictors:
        _predictors[cache_key] = Predictor(symbol, timeframe)
    return _predictors[cache_key]


def clear_predictor_cache() -> None:
    """Сбросить кэш предикторов (нужно при смене таймфрейма)."""
    _predictors.clear()
    logger.info("Кэш предикторов сброшен")
