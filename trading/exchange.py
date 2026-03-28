import ccxt
from loguru import logger

from config import config


def get_exchange(api_key: str = None, api_secret: str = None) -> ccxt.binance:
    """
    Создать подключение к торговой бирже.
    Если api_key/api_secret не переданы — используются ключи из .env.
    """
    exchange = ccxt.binance(
        {
            "apiKey": api_key or config.BINANCE_API_KEY,
            "secret": api_secret or config.BINANCE_API_SECRET,
            "options": {"defaultType": "future"},
            "adjustForTimeDifference": True,
        }
    )
    if config.BINANCE_TESTNET:
        exchange.set_sandbox_mode(True)
        logger.debug("Торговля: Binance TESTNET")
    else:
        logger.debug("Торговля: Binance PRODUCTION")
    return exchange


def get_exchange_for_user(user) -> ccxt.binance:
    """Создать биржевое подключение с ключами конкретного пользователя."""
    if not user.has_api_keys:
        raise ValueError(f"У пользователя {user.telegram_id} не настроены API ключи Binance")
    return get_exchange(api_key=user.get_api_key(), api_secret=user.get_api_secret())


def set_leverage(exchange: ccxt.binance, symbol: str, leverage: int) -> None:
    """Установить плечо для символа."""
    try:
        exchange.set_leverage(leverage, symbol)
        logger.info(f"Плечо {leverage}× установлено для {symbol}")
    except Exception as e:
        logger.warning(f"Не удалось установить плечо: {e}")


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
