from telegram import Bot
from telegram.constants import ParseMode

from config import config


async def send_message(text: str, parse_mode: str = ParseMode.HTML) -> int | None:
    """Отправить сообщение в Telegram. Возвращает message_id."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    msg = await bot.send_message(
        chat_id=config.TELEGRAM_CHAT_ID,
        text=text,
        parse_mode=parse_mode,
    )
    return msg.message_id


async def edit_message(message_id: int, text: str) -> None:
    """Редактировать существующее сообщение."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    await bot.edit_message_text(
        chat_id=config.TELEGRAM_CHAT_ID,
        message_id=message_id,
        text=text,
        parse_mode=ParseMode.HTML,
    )
