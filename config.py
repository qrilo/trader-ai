import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Binance
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
    BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: int = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

    # PostgreSQL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:traider@localhost:5432/traider"
    )

    # Параметры торговли
    RISK_PER_TRADE: float = float(os.getenv("RISK_PER_TRADE", "0.05"))
    MAX_OPEN_POSITIONS: int = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
    MIN_CONFIDENCE: float = float(os.getenv("MIN_CONFIDENCE", "0.65"))
    SIGNAL_TIMEOUT_MINUTES: int = int(os.getenv("SIGNAL_TIMEOUT_MINUTES", "10"))
    MIN_RR_RATIO: float = float(os.getenv("MIN_RR_RATIO", "2.0"))

    # Активы
    TRADING_SYMBOLS: list[str] = os.getenv(
        "TRADING_SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT"
    ).split(",")

    # Таймфрейм
    TIMEFRAME: str = os.getenv("TIMEFRAME", "15m")

    # Сколько исторических свечей загружать для анализа
    CANDLES_LIMIT: int = 500

    # Сколько лет исторических данных для обучения модели
    TRAINING_YEARS: int = 2

    def validate(self) -> None:
        errors = []
        if not self.BINANCE_API_KEY:
            errors.append("BINANCE_API_KEY не задан")
        if not self.BINANCE_API_SECRET:
            errors.append("BINANCE_API_SECRET не задан")
        if not self.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN не задан")
        if not self.TELEGRAM_CHAT_ID:
            errors.append("TELEGRAM_CHAT_ID не задан")
        if errors:
            raise ValueError("Ошибки конфигурации:\n" + "\n".join(errors))


config = Config()
