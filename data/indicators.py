import pandas as pd
import ta
from loguru import logger


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Добавить все технические индикаторы к датафрейму со свечами."""
    df = df.copy()

    # RSI — перекупленность/перепроданность
    df["rsi"] = ta.momentum.RSIIndicator(close=df["close"], window=14).rsi()

    # MACD — тренд и импульс
    macd = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    # Bollinger Bands — волатильность и уровни
    bb = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]

    # EMA — скользящие средние для определения тренда
    df["ema_20"] = ta.trend.EMAIndicator(close=df["close"], window=20).ema_indicator()
    df["ema_50"] = ta.trend.EMAIndicator(close=df["close"], window=50).ema_indicator()
    df["ema_200"] = ta.trend.EMAIndicator(close=df["close"], window=200).ema_indicator()

    # Объём
    df["volume_sma"] = ta.trend.SMAIndicator(close=df["volume"], window=20).sma_indicator()
    df["volume_ratio"] = df["volume"] / df["volume_sma"]

    # ATR — волатильность для расчёта SL
    df["atr"] = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=14
    ).average_true_range()

    # Stochastic RSI
    stoch = ta.momentum.StochRSIIndicator(close=df["close"], window=14, smooth1=3, smooth2=3)
    df["stoch_k"] = stoch.stochrsi_k()
    df["stoch_d"] = stoch.stochrsi_d()

    # Свечные паттерны
    df["candle_body"] = abs(df["close"] - df["open"])
    df["candle_range"] = df["high"] - df["low"]
    df["candle_body_ratio"] = df["candle_body"] / df["candle_range"].replace(0, 1)

    # Изменение цены
    df["price_change_1"] = df["close"].pct_change(1)
    df["price_change_3"] = df["close"].pct_change(3)
    df["price_change_5"] = df["close"].pct_change(5)

    df.dropna(inplace=True)

    logger.debug(f"Индикаторы рассчитаны, строк: {len(df)}")
    return df


def get_feature_columns() -> list[str]:
    """Список колонок-признаков для ML-модели."""
    return [
        "rsi",
        "macd",
        "macd_signal",
        "macd_hist",
        "bb_width",
        "ema_20",
        "ema_50",
        "volume_ratio",
        "atr",
        "stoch_k",
        "stoch_d",
        "candle_body_ratio",
        "price_change_1",
        "price_change_3",
        "price_change_5",
        "price_vs_ema20",
        "price_vs_ema50",
        "price_vs_ema200",
    ]


def add_price_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Добавить нормализованные признаки (цена относительно EMA)."""
    df = df.copy()
    df["price_vs_ema20"] = (df["close"] - df["ema_20"]) / df["ema_20"]
    df["price_vs_ema50"] = (df["close"] - df["ema_50"]) / df["ema_50"]
    df["price_vs_ema200"] = (df["close"] - df["ema_200"]) / df["ema_200"]
    return df
