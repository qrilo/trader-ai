from pathlib import Path
from typing import Optional

import joblib
import pandas as pd
from loguru import logger

from data.indicators import add_indicators, add_price_ratios


MODELS_DIR = Path(__file__).parent / "saved"


class Predictor:
    """Загружает обученную модель и делает предсказания."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.symbol_key = symbol.replace("/", "_")
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self._load()

    def _load(self) -> None:
        model_path = MODELS_DIR / f"{self.symbol_key}_model.pkl"
        scaler_path = MODELS_DIR / f"{self.symbol_key}_scaler.pkl"
        features_path = MODELS_DIR / f"{self.symbol_key}_features.pkl"

        if not model_path.exists():
            raise FileNotFoundError(
                f"Модель для {self.symbol} не найдена. Запустите обучение: train_all()"
            )

        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path)
        self.feature_columns = joblib.load(features_path)
        logger.debug(f"Модель {self.symbol} загружена")

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

            logger.debug(f"{self.symbol}: вероятность роста {proba:.3f}")
            return float(proba)

        except Exception as e:
            logger.error(f"Ошибка предсказания {self.symbol}: {e}")
            return None

    def is_model_available(self) -> bool:
        model_path = MODELS_DIR / f"{self.symbol_key}_model.pkl"
        return model_path.exists()


_predictors: dict[str, Predictor] = {}


def get_predictor(symbol: str) -> Predictor:
    """Кешированный доступ к предиктору."""
    if symbol not in _predictors:
        _predictors[symbol] = Predictor(symbol)
    return _predictors[symbol]
