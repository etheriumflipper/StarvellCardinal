"""
События чатов Starvell (аналог FunPay Cardinal runner events).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ChatEventType(str, Enum):
    INITIAL_CHAT = "initial_chat"
    CHATS_LIST_CHANGED = "chats_list_changed"
    LAST_CHAT_MESSAGE_CHANGED = "last_chat_message_changed"
    NEW_MESSAGE = "new_message"


@dataclass
class ChatShortcut:
    """Краткая информация о чате (как FunPay ChatShortcut)."""
    id: str
    name: Optional[str]
    last_message_text: str
    unread: bool
    companion_id: Optional[str] = None
    companion_username: Optional[str] = None
    order_id: Optional[str] = None
    last_message_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatMessage:
    """Сообщение в чате Starvell."""
    id: str
    chat_id: str
    author_id: str
    content: str
    author_username: Optional[str] = None
    author_roles: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    is_own: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BaseChatEvent:
    type: ChatEventType


@dataclass
class InitialChatEvent(BaseChatEvent):
    chat: ChatShortcut

    def __init__(self, chat: ChatShortcut):
        self.type = ChatEventType.INITIAL_CHAT
        self.chat = chat


@dataclass
class ChatsListChangedEvent(BaseChatEvent):
    def __init__(self):
        self.type = ChatEventType.CHATS_LIST_CHANGED


@dataclass
class LastChatMessageChangedEvent(BaseChatEvent):
    chat: ChatShortcut

    def __init__(self, chat: ChatShortcut):
        self.type = ChatEventType.LAST_CHAT_MESSAGE_CHANGED
        self.chat = chat


@dataclass
class NewMessageEvent(BaseChatEvent):
    message: ChatMessage
    chat: ChatShortcut

    def __init__(self, message: ChatMessage, chat: ChatShortcut):
        self.type = ChatEventType.NEW_MESSAGE
        self.message = message
        self.chat = chat


@dataclass
class ChatPollResult:
    """Результат одного цикла опроса чатов."""
    events: List[BaseChatEvent] = field(default_factory=list)
    legacy_messages: List[Dict[str, Any]] = field(default_factory=list)
    primed: bool = False


def message_sort_key(message: Dict[str, Any]) -> str:
    for key in ("createdAt", "created_at", "timestamp", "sentAt", "updatedAt", "date", "id"):
        value = message.get(key)
        if value is not None:
            return str(value)
    return ""


def sort_messages(messages: List[Dict[str, Any]], newest_first: bool = False) -> List[Dict[str, Any]]:
    ordered = sorted(messages, key=message_sort_key)
    if newest_first:
        ordered.reverse()
    return ordered


def extract_last_message_dict(chat: Dict[str, Any]) -> Dict[str, Any]:
    """Последнее сообщение чата (Starvell кладёт его в lastMessage, не в messages[])."""
    last_msg = chat.get("lastMessage")
    if isinstance(last_msg, dict):
        return last_msg

    messages = chat.get("messages") or []
    if isinstance(messages, list) and messages:
        return sort_messages(messages, newest_first=True)[0]

    if isinstance(last_msg, str) and last_msg:
        return {"content": last_msg}
    return {}


def extract_chat_messages(chat: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Сообщения из объекта чата: messages[] или одиночный lastMessage."""
    embedded = chat.get("messages") or []
    if isinstance(embedded, list) and embedded:
        return sort_messages(embedded)

    last_msg = extract_last_message_dict(chat)
    if last_msg.get("id") or last_msg.get("content") or last_msg.get("text"):
        return [last_msg]
    return []


def extract_companion(chat: Dict[str, Any], my_user_id: str = "") -> Dict[str, Any]:
    companion = chat.get("companion") or {}
    if companion:
        return companion

    members = chat.get("members") or chat.get("participants") or []
    for member in members:
        if isinstance(member, dict) and member.get("id"):
            return member

    last_msg = extract_last_message_dict(chat)
    for role in ("buyer", "seller", "admin"):
        user = last_msg.get(role)
        if isinstance(user, dict) and user.get("id"):
            return user

    for key in ("interlocutor", "user", "companionUser"):
        user = chat.get(key)
        if isinstance(user, dict) and user.get("id"):
            return user

    author_id = str(last_msg.get("authorId") or "")
    if author_id and my_user_id and author_id != my_user_id:
        return {"id": author_id}
    return {}


def build_chat_shortcut(chat: Dict[str, Any], my_user_id: str = "") -> ChatShortcut:
    companion = extract_companion(chat, my_user_id)
    last_msg = extract_last_message_dict(chat)
    preview = (
        last_msg.get("content")
        or last_msg.get("text")
        or chat.get("lastMessageText")
        or chat.get("last_message_text")
        or ""
    )
    order = chat.get("order") or {}
    if not order.get("id"):
        order_meta = (last_msg.get("metadata") or {})
        if order_meta.get("orderId"):
            order = {"id": order_meta.get("orderId")}
    unread = int(chat.get("unreadMessageCount") or chat.get("unreadCount") or 0) > 0
    return ChatShortcut(
        id=str(chat.get("id", "")),
        name=companion.get("username") or companion.get("name") or chat.get("title"),
        last_message_text=str(preview)[:250],
        unread=unread,
        companion_id=str(companion.get("id")) if companion.get("id") else None,
        companion_username=companion.get("username") or companion.get("name"),
        order_id=str(order.get("id")) if order.get("id") else None,
        last_message_id=str(last_msg.get("id")) if last_msg.get("id") else None,
        raw=chat,
    )


def build_chat_message(
    chat: Dict[str, Any],
    message: Dict[str, Any],
    my_user_id: str = "",
) -> ChatMessage:
    author_id = str(message.get("authorId") or message.get("author_id") or "")
    author_data = message.get("author") or {}
    author_username = author_data.get("username") or author_data.get("name")
    author_roles = author_data.get("roles") or []

    if not author_username:
        companion = extract_companion(chat, my_user_id)
        if author_id and str(companion.get("id")) == author_id:
            author_username = companion.get("username") or companion.get("name")

    if not author_username and chat:
        for participant in chat.get("participants") or []:
            if str(participant.get("id")) == author_id:
                author_username = participant.get("username") or participant.get("name")
                break

    content = message.get("content") or message.get("text") or ""
    return ChatMessage(
        id=str(message.get("id", "")),
        chat_id=str(chat.get("id", "")),
        author_id=author_id,
        content=content,
        author_username=author_username,
        author_roles=list(author_roles),
        created_at=message.get("createdAt") or message.get("created_at"),
        is_own=bool(my_user_id and author_id == my_user_id),
        raw=message,
    )


def message_to_plugin_data(message: ChatMessage, chat: ChatShortcut) -> Dict[str, Any]:
    """Словарь для BIND_TO_NEW_MESSAGE (обратная совместимость)."""
    return {
        "chat_id": message.chat_id,
        "author": message.author_id,
        "author_username": message.author_username,
        "author_roles": message.author_roles,
        "content": message.content,
        "message_id": message.id,
        "created_at": message.created_at,
        "is_own": message.is_own,
        "companion_id": chat.companion_id,
        "companion_username": chat.companion_username,
        "order_id": chat.order_id,
        "unread": chat.unread,
        "chat": chat.raw,
        "message": message.raw,
    }
