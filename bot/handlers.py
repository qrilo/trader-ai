from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import config
from database import repository
from database.models import SignalStatus


def build_signal_keyboard(signal_id: int) -> InlineKeyboardMarkup:
    """Клавиатура апрува под карточкой сигнала."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Войти", callback_data=f"approve:{signal_id}"),
            InlineKeyboardButton("❌ Пропустить", callback_data=f"reject:{signal_id}"),
        ]
    ])


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать нажатие кнопки под сигналом."""
    query = update.callback_query
    await query.answer()

    # Проверяем что нажал именно наш пользователь
    if update.effective_user.id != config.TELEGRAM_CHAT_ID:
        await query.answer("⛔️ Нет доступа", show_alert=True)
        return

    action, signal_id_str = query.data.split(":")
    signal_id = int(signal_id_str)
    signal = repository.get_signal(signal_id)

    if signal is None:
        await query.edit_message_text("⚠️ Сигнал не найден")
        return

    if signal.status != SignalStatus.PENDING:
        status_text = {
            SignalStatus.APPROVED: "уже исполнен",
            SignalStatus.REJECTED: "уже отклонён",
            SignalStatus.EXPIRED: "истёк",
        }.get(signal.status, "обработан")
        await query.edit_message_text(f"ℹ️ Сигнал #{signal_id} {status_text}")
        return

    if action == "approve":
        await _handle_approve(query, signal_id, signal)
    elif action == "reject":
        await _handle_reject(query, signal_id, signal)


async def _handle_approve(query, signal_id: int, signal) -> None:
    """Апрув сигнала — исполняем ордер на бирже."""
    from trading.order_manager import execute_signal

    logger.info(f"Пользователь апрувнул сигнал #{signal_id}")
    await query.edit_message_text(
        f"⏳ Исполняю ордер {signal.symbol} {signal.direction.value}...",
    )

    try:
        trade = await execute_signal(signal)
        repository.update_signal_status(signal_id, SignalStatus.APPROVED)

        await query.edit_message_text(
            f"✅ <b>Ордер исполнен!</b>\n\n"
            f"📌 {signal.symbol} {signal.direction.value}\n"
            f"📈 Вход: <b>${trade.entry_price:,.2f}</b>\n"
            f"🛑 SL: <b>${trade.stop_loss:,.2f}</b>\n"
            f"🎯 TP: <b>${trade.take_profit:,.2f}</b>\n\n"
            f"Слежу за позицией и сообщу о результате.",
            parse_mode="HTML",
        )
        logger.info(f"Сигнал #{signal_id} исполнен, сделка #{trade.id}")
    except Exception as e:
        logger.error(f"Ошибка исполнения сигнала #{signal_id}: {e}")
        await query.edit_message_text(
            f"❌ <b>Ошибка исполнения ордера</b>\n\n{e}",
            parse_mode="HTML",
        )


async def _handle_reject(query, signal_id: int, signal) -> None:
    """Отклонение сигнала пользователем."""
    logger.info(f"Пользователь отклонил сигнал #{signal_id}")
    repository.update_signal_status(signal_id, SignalStatus.REJECTED)
    await query.edit_message_text(
        f"🚫 Сигнал #{signal_id} <b>{signal.symbol} {signal.direction.value}</b> отклонён",
        parse_mode="HTML",
    )
