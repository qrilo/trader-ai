from datetime import datetime, timedelta

import ccxt
import pandas as pd
from loguru import logger

from config import config


def _normalize_timeframe(tf: str) -> str:
    """У Binance Futures нет интервала 10m — подставляем 15m."""
    if tf == "10m":
        return "15m"
    return tf


def _get_data_exchange() -> ccxt.binance:
    """Биржа для публичных данных (свечи, цены) — ключи не нужны."""
    return ccxt.binance({
        "options": {"defaultType": "future"},
        "adjustForTimeDifference": True,
    })


def fetch_candles(symbol: str, timeframe: str = None, limit: int = None) -> pd.DataFrame:
    """Получить последние свечи для символа с реального Binance."""
    timeframe = _normalize_timeframe(timeframe or config.TIMEFRAME)
    limit = limit or config.CANDLES_LIMIT

    exchange = _get_data_exchange()
    exchange.load_time_difference()
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        logger.debug(f"Загружено {len(df)} свечей {symbol} ({timeframe})")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки свечей {symbol}: {e}")
        raise


def fetch_historical_candles(symbol: str, timeframe: str = "15m", years: int = 2) -> pd.DataFrame:
    """
    Загрузить исторические данные для обучения модели.
    Всегда с реального Binance — там настоящие рыночные данные.
    API ключи для этого не нужны.
    """
    timeframe = _normalize_timeframe(timeframe)
    exchange = _get_data_exchange()

    # Синхронизируем время с сервером Binance перед загрузкой
    logger.info(f"  Синхронизация времени с Binance...")
    exchange.load_time_difference()

    since = int((datetime.utcnow() - timedelta(days=365 * years)).timestamp() * 1000)
    all_candles = []
    batch = 0

    logger.info(f"  Источник: Binance (реальный рынок, не Testnet)")

    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv:
                break

            all_candles.extend(ohlcv)
            since = ohlcv[-1][0] + 1
            batch += 1

            if batch % 10 == 0:
                loaded = len(all_candles)
                first_date = datetime.utcfromtimestamp(all_candles[0][0] / 1000).strftime("%Y-%m")
                last_date = datetime.utcfromtimestamp(all_candles[-1][0] / 1000).strftime("%Y-%m")
                logger.info(f"  Загружено: {loaded:,} свечей ({first_date} → {last_date})")

            if len(ohlcv) < 1000:
                break
        except Exception as e:
            logger.error(f"Ошибка загрузки исторических данных: {e}")
            break

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    df.drop_duplicates(inplace=True)
    df.sort_index(inplace=True)

    return df



def get_current_price(symbol: str) -> float:
    """Получить текущую цену символа с реального рынка."""
    exchange = _get_data_exchange()
    ticker = exchange.fetch_ticker(symbol)
    return float(ticker["last"])
