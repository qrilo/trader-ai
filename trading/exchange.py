import ccxt
from loguru import logger

from config import config


def get_exchange() -> ccxt.binance:
    """
    Создать подключение к торговой бирже.
    Testnet — для тестирования без реальных денег.
    Production — для реальной торговли.
    Данные (свечи, цены) всегда берём с реального Binance отдельно.
    """
    exchange = ccxt.binance(
        {
            "apiKey": config.BINANCE_API_KEY,
            "secret": config.BINANCE_API_SECRET,
            "options": {"defaultType": "future"},
            "adjustForTimeDifference": True,  # автоматически синхронизирует время с сервером
        }
    )
    if config.BINANCE_TESTNET:
        exchange.set_sandbox_mode(True)
        logger.debug("Торговля: Binance TESTNET")
    else:
        logger.debug("Торговля: Binance PRODUCTION")
    return exchange


def _sync_time() -> ccxt.binance:
    """Получить биржу с синхронизированным временем."""
    exchange = get_exchange()
    exchange.load_time_difference()
    return exchange


def place_market_order(symbol: str, side: str, quantity: float) -> dict:
    """
    Выставить рыночный ордер.
    side: 'buy' для LONG, 'sell' для SHORT
    """
    exchange = _sync_time()
    order = exchange.create_order(
        symbol=symbol,
        type="market",
        side=side,
        amount=quantity,
    )
    logger.info(f"Рыночный ордер: {symbol} {side} {quantity} → ID: {order['id']}")
    return order


def place_stop_loss_order(symbol: str, side: str, quantity: float, stop_price: float) -> dict:
    """
    Выставить стоп-лосс ордер.
    Для LONG позиции side='sell', для SHORT — side='buy'.
    """
    exchange = _sync_time()
    order = exchange.create_order(
        symbol=symbol,
        type="stop_market",
        side=side,
        amount=quantity,
        params={"stopPrice": stop_price, "reduceOnly": True},
    )
    logger.info(f"Stop Loss ордер: {symbol} {side} @ ${stop_price} → ID: {order['id']}")
    return order


def place_take_profit_order(symbol: str, side: str, quantity: float, tp_price: float) -> dict:
    """Выставить тейк-профит ордер."""
    exchange = _sync_time()
    order = exchange.create_order(
        symbol=symbol,
        type="take_profit_market",
        side=side,
        amount=quantity,
        params={"stopPrice": tp_price, "reduceOnly": True},
    )
    logger.info(f"Take Profit ордер: {symbol} {side} @ ${tp_price} → ID: {order['id']}")
    return order


def cancel_order(symbol: str, order_id: str) -> None:
    """Отменить ордер."""
    exchange = get_exchange()
    exchange.cancel_order(order_id, symbol)
    logger.info(f"Ордер {order_id} отменён")


def get_order_status(symbol: str, order_id: str) -> dict:
    """Получить статус ордера."""
    exchange = get_exchange()
    return exchange.fetch_order(order_id, symbol)
