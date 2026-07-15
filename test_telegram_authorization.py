import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot

from telegram.ext import ApplicationHandlerStop


def _message_update(chat_id):
    return SimpleNamespace(
        effective_chat=(SimpleNamespace(id=chat_id) if chat_id is not None else None),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
        callback_query=None,
    )


def _callback_update(chat_id):
    callback_query = SimpleNamespace(answer=AsyncMock())
    return SimpleNamespace(
        effective_chat=(SimpleNamespace(id=chat_id) if chat_id is not None else None),
        effective_message=None,
        callback_query=callback_query,
    )


class TelegramAuthorizationGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorized_command_is_forwarded(self):
        update = _message_update(12345)
        downstream_handler = AsyncMock()

        with patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "12345"}):
            await telegram_bot._authorization_gate(update, None)
            await downstream_handler(update)

        downstream_handler.assert_awaited_once_with(update)
        update.effective_message.reply_text.assert_not_awaited()

    async def test_unauthorized_command_is_stopped(self):
        update = _message_update(99999)

        with patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "12345"}):
            with self.assertRaises(ApplicationHandlerStop):
                await telegram_bot._authorization_gate(update, None)

        update.effective_message.reply_text.assert_awaited_once_with(
            "⛔ Unauthorized."
        )

    async def test_unauthorized_callback_is_stopped_with_alert(self):
        update = _callback_update(99999)

        with patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "12345"}):
            with self.assertRaises(ApplicationHandlerStop):
                await telegram_bot._authorization_gate(update, None)

        update.callback_query.answer.assert_awaited_once_with(
            "⛔ Unauthorized.",
            show_alert=True,
        )

    async def test_sensitive_handler_is_not_called_after_rejection(self):
        update = _message_update(99999)
        sensitive_handler = AsyncMock()

        with patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "12345"}):
            try:
                await telegram_bot._authorization_gate(update, None)
            except ApplicationHandlerStop:
                pass
            else:
                await sensitive_handler(update)

        sensitive_handler.assert_not_awaited()

    async def test_empty_telegram_chat_id_is_rejected(self):
        update = _message_update(12345)

        with patch.dict(os.environ, {"TELEGRAM_CHAT_ID": ""}):
            with self.assertRaises(ApplicationHandlerStop):
                await telegram_bot._authorization_gate(update, None)

        update.effective_message.reply_text.assert_awaited_once_with(
            "⛔ Unauthorized."
        )

    async def test_update_without_effective_chat_is_safely_stopped(self):
        update = SimpleNamespace(
            effective_chat=None,
            effective_message=None,
            callback_query=None,
        )

        with patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "12345"}):
            with self.assertRaises(ApplicationHandlerStop):
                await telegram_bot._authorization_gate(update, None)


if __name__ == "__main__":
    unittest.main()
