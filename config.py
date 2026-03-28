import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    TELEGRAM_WHITELIST: list[int] = [
        int(x.strip())
        for x in os.getenv("TELEGRAM_WHITELIST", "").split(",")
        if x.strip().isdigit()
    ]

    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:traider@localhost:5432/traider"
    )

    TRADING_SYMBOLS: list[str] = os.getenv("TRADING_SYMBOLS", "BTC/USDT").split(",")

    # Таймфрейм при первом запуске (потом меняется через бота ⚙️ Настройки)
    TIMEFRAME: str = os.getenv("TIMEFRAME", "15m")

    # Интервалы из справочника Binance (10m у биржи нет — дефолт 15m)
    SUPPORTED_TIMEFRAMES: dict = {
        "1m": 1,
        "3m": 3,
        "5m": 5,
        "15m": 15,
    }

    CANDLES_LIMIT: int = 500
    TRAINING_YEARS: int = 2

    # Дефолтные торговые настройки для новых пользователей
    DEFAULT_MARGIN_USDT: float = float(os.getenv("DEFAULT_MARGIN_USDT", "50"))
    DEFAULT_SL_PERCENT: float = float(os.getenv("DEFAULT_SL_PERCENT", "1.5"))
    DEFAULT_TP_PERCENT: float = float(os.getenv("DEFAULT_TP_PERCENT", "3.0"))
    DEFAULT_MAX_OPEN_POSITIONS: int = 3
    DEFAULT_MIN_CONFIDENCE: float = 0.65
    DEFAULT_SIGNAL_TIMEOUT_MINUTES: int = 10
    DEFAULT_MIN_RR_RATIO: float = 2.0

    # Подробные причины отказа в генерации сигнала (stdout INFO); иначе только DEBUG в traider.log
    VERBOSE_SIGNAL_ANALYSIS: bool = os.getenv("VERBOSE_SIGNAL_ANALYSIS", "false").lower() == "true"

    def validate(self) -> None:
        errors = []
        if not self.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN не задан")
        if not self.TELEGRAM_WHITELIST:
            errors.append("TELEGRAM_WHITELIST не задан — добавь хотя бы один Telegram ID")
        if not self.ENCRYPTION_KEY:
            import warnings
            warnings.warn(
                "ENCRYPTION_KEY не задан — Binance ключи хранятся без шифрования! "
                "Сгенерируй: docker compose run --rm traider python -c "
                "\"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        if errors:
            raise ValueError("Ошибки конфигурации:\n" + "\n".join(errors))


config = Config()
