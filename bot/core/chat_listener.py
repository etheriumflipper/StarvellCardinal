"""
Опрос чатов Starvell — аналог FunPay Cardinal Runner для сообщений.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from bot.core.chat_events import (
    ChatPollResult,
    ChatShortcut,
    ChatsListChangedEvent,
    InitialChatEvent,
    LastChatMessageChangedEvent,
    NewMessageEvent,
    build_chat_message,
    build_chat_shortcut,
    message_sort_key,
    message_to_plugin_data,
    sort_messages,
)

if TYPE_CHECKING:
    from bot.core.services import StarvellService

logger = logging.getLogger(__name__)


class ChatListener:
    """Слушатель входящих сообщений в ЛС/чатах заказов."""

    def __init__(self, service: "StarvellService"):
        self.service = service
        self._first_request = True
        self._known_chats: Dict[str, ChatShortcut] = {}

    async def poll(self, prime_only: bool = False) -> ChatPollResult:
        result = ChatPollResult()
        my_user_id = await self._get_my_user_id()
        chats = await self.service.get_chats()

        list_changed = False
        changed_chats: List[ChatShortcut] = []

        for chat in chats:
            chat_id = str(chat.get("id") or "")
            if not chat_id:
                continue

            shortcut = build_chat_shortcut(chat)
            prev = self._known_chats.get(chat_id)

            if self._first_request:
                await self._prime_chat(chat_id, chat, my_user_id)
                result.events.append(InitialChatEvent(shortcut))
                self._known_chats[chat_id] = shortcut
                continue

            if prev is None and not self._first_request:
                list_changed = True
                changed_chats.append(shortcut)
                result.events.append(LastChatMessageChangedEvent(shortcut))
            elif prev and (
                prev.last_message_id != shortcut.last_message_id
                or prev.last_message_text != shortcut.last_message_text
                or prev.unread != shortcut.unread
            ):
                list_changed = True
                changed_chats.append(shortcut)
                result.events.append(LastChatMessageChangedEvent(shortcut))

            self._known_chats[chat_id] = shortcut

        if self._first_request:
            self._first_request = False
            result.primed = True
            logger.info(
                "🧊 Первый запуск: кэш сообщений прогрет (%s чатов), события не отправляются",
                len(chats),
            )
            return result

        if list_changed:
            result.events.insert(0, ChatsListChangedEvent())

        if prime_only:
            return result

        for shortcut in changed_chats:
            chat = shortcut.raw
            chat_id = shortcut.id
            messages = await self._resolve_messages(chat_id, chat, shortcut)
            if not messages:
                continue

            last_known_id = await self.service.db.get_last_message(chat_id)
            new_raw_messages = self._collect_new_messages(messages, last_known_id)
            if not new_raw_messages and shortcut.unread:
                new_raw_messages = self._collect_incoming_preview(messages, my_user_id, shortcut)

            latest_id = sort_messages(messages, newest_first=True)[0].get("id")
            if latest_id:
                await self.service.db.set_last_message(chat_id, str(latest_id))

            for raw_msg in new_raw_messages:
                msg = build_chat_message(chat, raw_msg, my_user_id)
                if msg.is_own:
                    continue
                if not msg.content and not raw_msg.get("attachments"):
                    continue

                result.events.append(NewMessageEvent(msg, shortcut))
                result.legacy_messages.append({
                    "chat_id": chat_id,
                    "message": raw_msg,
                    "chat": chat,
                    "plugin_data": message_to_plugin_data(msg, shortcut),
                })

        return result

    async def _prime_chat(self, chat_id: str, chat: Dict[str, Any], my_user_id: str) -> None:
        messages = await self._resolve_messages(chat_id, chat, build_chat_shortcut(chat))
        if messages:
            latest_id = sort_messages(messages, newest_first=True)[0].get("id")
            if latest_id:
                await self.service.db.set_last_message(chat_id, str(latest_id))

    async def _resolve_messages(
        self,
        chat_id: str,
        chat: Dict[str, Any],
        shortcut: ChatShortcut,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        embedded = chat.get("messages") or []
        if isinstance(embedded, list) and embedded:
            sorted_embedded = sort_messages(embedded, newest_first=True)
            unread = int(chat.get("unreadMessageCount") or chat.get("unreadCount") or 0)
            if unread <= len(sorted_embedded):
                return sort_messages(embedded)

        last_known_id = await self.service.db.get_last_message(chat_id)
        if last_known_id and embedded:
            ids = {str(m.get("id")) for m in embedded if m.get("id")}
            if last_known_id in ids:
                return sort_messages(embedded)

        try:
            full = await self.service.get_chat_messages(chat_id, limit=limit)
            if full:
                return full
        except Exception as exc:
            logger.debug(f"Не удалось загрузить историю чата {chat_id}: {exc}")

        return sort_messages(embedded) if embedded else []

    def _collect_new_messages(
        self,
        messages: List[Dict[str, Any]],
        last_known_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        if not messages:
            return []

        ordered = sort_messages(messages)
        if not last_known_id:
            return ordered

        new_messages: List[Dict[str, Any]] = []
        passed = False
        for msg in ordered:
            msg_id = str(msg.get("id") or "")
            if not passed:
                if msg_id == str(last_known_id):
                    passed = True
                continue
            new_messages.append(msg)

        if not new_messages and ordered:
            latest_id = str(ordered[-1].get("id") or "")
            if latest_id and latest_id != str(last_known_id):
                return [ordered[-1]]

        return new_messages

    def _collect_incoming_preview(
        self,
        messages: List[Dict[str, Any]],
        my_user_id: str,
        shortcut: ChatShortcut,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        incoming = []
        for msg in sort_messages(messages, newest_first=True):
            author_id = str(msg.get("authorId") or "")
            if my_user_id and author_id == my_user_id:
                continue
            content = msg.get("content") or msg.get("text") or ""
            if content or msg.get("attachments"):
                incoming.append(msg)
            if len(incoming) >= limit:
                break
        return list(reversed(incoming))

    async def _get_my_user_id(self) -> str:
        info = self.service.last_user_info or await self.service.get_user_info()
        return str((info.get("user") or {}).get("id", ""))
