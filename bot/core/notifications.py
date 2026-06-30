"""
Система уведомлений Starvell Cardinal
"""

import logging
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.core.config import BotConfig
from api.utils import safe_float

logger = logging.getLogger(__name__)


class NotificationType:
    """Типы уведомлений"""
    NEW_MESSAGE = "new_message"
    SUPPORT_MESSAGE = "support_message"
    NEW_ORDER = "new_order"
    ORDER_CONFIRMED = "order_confirmed"
    ORDER_CANCELLED = "order_cancelled"
    LOT_DEACTIVATED = "lot_deactivated"
    LOT_RESTORED = "lot_restored"
    LOT_BUMPED = "lot_bumped"
    BOT_STARTED = "bot_started"
    BOT_STOPPED = "bot_stopped"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    AUTO_DELIVERY = "auto_delivery"
    AUTO_RESTORE = "auto_restore"
    AUTO_BUMP = "auto_bump"
    UPDATE_AVAILABLE = "update_available"


class NotificationManager:
    """Менеджер уведомлений"""
    
    # Эмодзи для разных типов уведомлений
    EMOJI_MAP = {
        NotificationType.NEW_MESSAGE: "💬",
        NotificationType.SUPPORT_MESSAGE: "🛡️",
        NotificationType.NEW_ORDER: "📦",
        NotificationType.ORDER_CONFIRMED: "✅",
        NotificationType.ORDER_CANCELLED: "❌",
        NotificationType.LOT_DEACTIVATED: "🚫",
        NotificationType.LOT_RESTORED: "🔄",
        NotificationType.LOT_BUMPED: "⬆️",
        NotificationType.BOT_STARTED: "🟢",
        NotificationType.BOT_STOPPED: "🔴",
        NotificationType.ERROR: "❌",
        NotificationType.WARNING: "⚠️",
        NotificationType.UPDATE_AVAILABLE: "✨",
        NotificationType.INFO: "ℹ️",
        NotificationType.AUTO_DELIVERY: "🤖",
        NotificationType.AUTO_RESTORE: "♻️",
        NotificationType.AUTO_BUMP: "🔀",
    }
    
    # Заголовки для разных типов
    TITLE_MAP = {
        NotificationType.NEW_MESSAGE: "Новое сообщение",
        NotificationType.SUPPORT_MESSAGE: "Сообщение от поддержки",
        NotificationType.NEW_ORDER: "Новый заказ",
        NotificationType.ORDER_CONFIRMED: "Заказ подтверждён",
        NotificationType.ORDER_CANCELLED: "Заказ отменён",
        NotificationType.LOT_DEACTIVATED: "Лот деактивирован",
        NotificationType.LOT_RESTORED: "Лот восстановлен",
        NotificationType.LOT_BUMPED: "Лот поднят",
        NotificationType.BOT_STARTED: "Бот запущен",
        NotificationType.BOT_STOPPED: "Бот остановлен",
        NotificationType.ERROR: "Ошибка",
        NotificationType.WARNING: "Предупреждение",
        NotificationType.INFO: "Информация",
        NotificationType.AUTO_DELIVERY: "Автовыдача",
        NotificationType.AUTO_RESTORE: "Авто-восстановление",
        NotificationType.AUTO_BUMP: "Авто-поднятие",
    }
    
    def __init__(self, bot: Bot, starvell_service=None):
        self.bot = bot
        self._enabled_notifications: Dict[int, Dict[str, bool]] = {}
        self.plugin_manager = None  # Будет установлен позже
        self.starvell_service = starvell_service  # Ссылка на сервис Starvell
        self._nickname_cache: Dict[str, str] = {}  # Кэш nickname: user_id -> nickname

    @staticmethod
    def _normalize_chat_id(chat_id: Any) -> str:
        """Вернуть UUID чата в строковом виде или пустую строку."""
        if chat_id is None:
            return ""

        chat_id = str(chat_id).strip()
        if not chat_id:
            return ""

        try:
            return str(uuid.UUID(chat_id))
        except (ValueError, AttributeError, TypeError):
            return ""

    async def _resolve_order_chat_id(self, order_data: Optional[dict]) -> str:
        """Получить реальный UUID чата для заказа, а не buyerId."""
        if not order_data:
            return ""

        direct_candidates = [
            order_data.get("chat_id"),
            order_data.get("chatId"),
            (order_data.get("chat") or {}).get("id") if isinstance(order_data.get("chat"), dict) else None,
        ]

        for candidate in direct_candidates:
            normalized = self._normalize_chat_id(candidate)
            if normalized:
                order_data["chat_id"] = normalized
                return normalized

        order_id = str(order_data.get("id", "")).strip()
        if self.starvell_service and order_id:
            try:
                details = await self.starvell_service.get_order_details(order_id)
                page_props = details.get("pageProps", {}) if isinstance(details, dict) else {}
                chat_data = page_props.get("chat", {}) if isinstance(page_props, dict) else {}
                order_info = page_props.get("order", {}) if isinstance(page_props, dict) else {}

                detail_candidates = [
                    chat_data.get("id") if isinstance(chat_data, dict) else None,
                    order_info.get("chatId") if isinstance(order_info, dict) else None,
                    details.get("chat_id") if isinstance(details, dict) else None,
                    details.get("chatId") if isinstance(details, dict) else None,
                ]

                for candidate in detail_candidates:
                    normalized = self._normalize_chat_id(candidate)
                    if normalized:
                        order_data["chat_id"] = normalized
                        return normalized
            except Exception as e:
                logger.debug(f"Не удалось получить chat_id из деталей заказа {order_id}: {e}")

        buyer_data = order_data.get("user") or order_data.get("buyer") or {}
        buyer_id = order_data.get("buyerId")
        if not buyer_id and isinstance(buyer_data, dict):
            buyer_id = buyer_data.get("id")

        if self.starvell_service and buyer_id:
            try:
                resolved_chat_id = await self.starvell_service.find_chat_by_user_id(str(buyer_id))
                normalized = self._normalize_chat_id(resolved_chat_id)
                if normalized:
                    order_data["chat_id"] = normalized
                    return normalized
            except Exception as e:
                logger.debug(f"Не удалось найти chat_id по buyerId={buyer_id}: {e}")

        return ""
    
    async def _get_nickname_by_id(self, user_id: str) -> Optional[str]:
        """
        Получить nickname пользователя по ID (с кэшированием)
        
        Args:
            user_id: ID пользователя
            
        Returns:
            str: Nickname или None если не найден
        """
        # Проверяем кэш
        if user_id in self._nickname_cache:
            return self._nickname_cache[user_id]
        
        # Если нет starvell_service - возвращаем None
        if not self.starvell_service:
            return None
        
        try:
            # Запрашиваем профиль через API
            profile = await self.starvell_service.get_user_profile(user_id)
            if profile:
                nickname = profile.get("nickname") or profile.get("username") or profile.get("name")
                if nickname:
                    # Сохраняем в кэш
                    self._nickname_cache[user_id] = nickname
                    logger.debug(f"Получен nickname для {user_id}: {nickname}")
                    return nickname
        except Exception as e:
            logger.debug(f"Ошибка получения nickname для {user_id}: {e}")
        
        return None
        
    def _check_notification_enabled(self, user_id: int, notif_type: str) -> bool:
        """Проверка, включён ли тип уведомления для пользователя"""
        # Маппинг типов на настройки конфига
        config_map = {
            NotificationType.NEW_MESSAGE: BotConfig.NOTIFY_NEW_MESSAGES,
            NotificationType.SUPPORT_MESSAGE: BotConfig.NOTIFY_SUPPORT_MESSAGES,
            NotificationType.NEW_ORDER: BotConfig.NOTIFY_NEW_ORDERS,
            NotificationType.LOT_RESTORED: BotConfig.NOTIFY_LOT_RESTORE,
            NotificationType.LOT_BUMPED: BotConfig.NOTIFY_LOT_BUMP,
            NotificationType.LOT_DEACTIVATED: BotConfig.NOTIFY_LOT_DEACTIVATE,
            NotificationType.BOT_STARTED: BotConfig.NOTIFY_BOT_START,
            NotificationType.BOT_STOPPED: BotConfig.NOTIFY_BOT_STOP,
            NotificationType.ORDER_CONFIRMED: BotConfig.NOTIFY_ORDER_CONFIRMED,
        }
        
        # Если есть соответствующая настройка в конфиге
        if notif_type in config_map:
            return config_map[notif_type]()
        
        # По умолчанию включено
        return True
    
    async def send_notification(
        self,
        user_id: int,
        notif_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        keyboard: Optional[InlineKeyboardMarkup] = None,
        force: bool = False
    ) -> bool:
        """
        Отправить уведомление пользователю
        
        Args:
            user_id: ID пользователя
            notif_type: Тип уведомления из NotificationType
            message: Текст сообщения
            details: Дополнительные детали для форматирования
            keyboard: Клавиатура (опционально)
            force: Отправить принудительно, игнорируя настройки
            
        Returns:
            True если уведомление отправлено успешно
        """
        # Проверяем настройки уведомлений
        if not force and not self._check_notification_enabled(user_id, notif_type):
            logger.debug(f"Уведомление {notif_type} для {user_id} отключено")
            return False
        
        try:
            # Формируем текст уведомления
            emoji = self.EMOJI_MAP.get(notif_type, "📌")
            title = self.TITLE_MAP.get(notif_type, "Уведомление")
            
            text = f"{emoji} <b>{title}</b>\n\n"
            text += message
            
            # Добавляем детали если есть
            if details:
                text += "\n\n"
                for key, value in details.items():
                    text += f"<b>{key}:</b> {value}\n"
            
            # Отправляем
            await self.bot.send_message(
                user_id,
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            logger.debug(f"Уведомление {notif_type} отправлено пользователю {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление {notif_type} пользователю {user_id}: {e}")
            return False
    
    async def notify_all_admins(
        self,
        notif_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        keyboard: Optional[InlineKeyboardMarkup] = None,
        force: bool = False
    ) -> int:
        """
        Отправить уведомление всем админам
        
        Returns:
            Количество успешно отправленных уведомлений
        """
        count = 0
        for admin_id in BotConfig.ADMIN_IDS():
            if await self.send_notification(admin_id, notif_type, message, details, keyboard, force):
                count += 1
        return count
    
    async def notify_new_message(
        self,
        chat_id: str,
        author: str,
        content: str,
        message_id: Optional[str] = None,
        author_nickname: Optional[str] = None
    ):
        """Уведомление о новом сообщении"""
        from bot.keyboards.keyboards import get_select_template_menu
        from bot.core.templates import get_template_manager
        
        # Используем nickname если есть, иначе ID
        display_name = author_nickname if author_nickname else author
        
        # Форматируем сообщение: смайлик + nickname/ID: message
        message = f"💬 <b>{display_name}:</b> {content}"
        
        # Создаём кнопки
        buttons = []

        # Формируем первую строку: Ответить + Быстрые ответы (если есть chat_id)
        row1 = []

        # Кнопка "Ответить" - используем полный chat_id (UUID или numeric)
        if chat_id:
            reply_callback = f"r:{chat_id}"
            # Telegram callback_data limit is 64 bytes; UUIDs are short enough
            if len(reply_callback) <= 64:
                row1.append(
                    InlineKeyboardButton(
                        text="💬 Ответить",
                        callback_data=reply_callback
                    )
                )

        # Проверяем количество заготовок
        template_manager = get_template_manager()
        templates_count = template_manager.count()

        # Кнопка "Быстрые ответы" — показываем всегда, если есть chat_id
        if chat_id:
            tpl_text = f"📝 Быстрые ответы ({templates_count})" if templates_count > 0 else "📝 Быстрые ответы"
            tpl_callback = f"show_templates:{chat_id}"
            # Проверяем длину callback_data (лимит Telegram - 64 байта)
            if len(tpl_callback.encode('utf-8')) <= 64:
                row1.append(
                    InlineKeyboardButton(
                        text=tpl_text,
                        callback_data=tpl_callback
                    )
                )
            else:
                logger.warning(f"Callback data для быстрых ответов слишком длинный: {len(tpl_callback.encode('utf-8'))} байт (chat_id: {chat_id[:20]}...)")

        if row1:
            buttons.append(row1)

        # Кнопка "Перейти в чат" - URL кнопка (в новой строке)
        chat_url = f"https://starvell.com/chat/{chat_id}"
        buttons.append([
            InlineKeyboardButton(
                text="🔗 Перейти в чат",
                url=chat_url
            )
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        
        await self.notify_all_admins(
            NotificationType.NEW_MESSAGE,
            message,
            keyboard=keyboard
        )
        
        # Вызываем хэндлеры плагинов для новых сообщений
        # Передаём реальный author ID, а не display_name
        await self._run_plugin_handlers_for_new_message(
            chat_id,
            author,  # Передаём оригинальный ID автора
            content,
            message_id
        )
    
    async def notify_support_message(
        self,
        chat_id: str,
        author: str,
        content: str,
        message_id: Optional[str] = None,
        author_nickname: Optional[str] = None,
        author_roles: Optional[List[str]] = None
    ):
        """Уведомление о сообщении от поддержки/модерации"""
        from bot.keyboards.keyboards import get_select_template_menu
        from bot.core.templates import get_template_manager
        
        # Используем nickname если есть, иначе ID
        display_name = author_nickname if author_nickname else author
        
        # Определяем роль для отображения
        role_emoji = "🛡️"
        role_name = "Поддержка"
        
        if author_roles:
            if "SUPPORT" in author_roles:
                role_emoji = "🛡️"
                role_name = "Поддержка"
            elif "MODERATOR" in author_roles or "ADMIN" in author_roles:
                role_emoji = "⚔️"
                role_name = "Модератор"
        
        # Форматируем сообщение с указанием роли
        message = f"{role_emoji} <b>{role_name} - {display_name}:</b>\n\n{content}"
        
        # Создаём кнопки
        buttons = []

        # Формируем первую строку: Ответить + Быстрые ответы (если есть chat_id)
        row1 = []

        # Кнопка "Ответить" - используем полный chat_id (UUID или numeric)
        if chat_id:
            reply_callback = f"r:{chat_id}"
            # Telegram callback_data limit is 64 bytes; UUIDs are short enough
            if len(reply_callback) <= 64:
                row1.append(
                    InlineKeyboardButton(
                        text="💬 Ответить",
                        callback_data=reply_callback
                    )
                )

        # Проверяем количество заготовок
        template_manager = get_template_manager()
        templates_count = template_manager.count()

        # Кнопка "Быстрые ответы" — показываем всегда, если есть chat_id
        if chat_id:
            tpl_text = f"📝 Быстрые ответы ({templates_count})" if templates_count > 0 else "📝 Быстрые ответы"
            tpl_callback = f"show_templates:{chat_id}"
            # Проверяем длину callback_data (лимит Telegram - 64 байта)
            if len(tpl_callback.encode('utf-8')) <= 64:
                row1.append(
                    InlineKeyboardButton(
                        text=tpl_text,
                        callback_data=tpl_callback
                    )
                )
            else:
                logger.warning(f"Callback data для быстрых ответов слишком длинный: {len(tpl_callback.encode('utf-8'))} байт (chat_id: {chat_id[:20]}...)")

        if row1:
            buttons.append(row1)

        # Кнопка "Перейти в чат" - URL кнопка (в новой строке)
        chat_url = f"https://starvell.com/chat/{chat_id}"
        buttons.append([
            InlineKeyboardButton(
                text="🔗 Перейти в чат",
                url=chat_url
            )
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        
        await self.notify_all_admins(
            NotificationType.SUPPORT_MESSAGE,
            message,
            keyboard=keyboard
        )
    
    async def notify_new_order(
        self,
        order_id: str,
        short_id: str,
        buyer: str,
        amount: float,
        lot_name: str,
        status: str = "CREATED",
        order_data: dict = None
    ):
        """Уведомление о новом заказе"""
        from bot.keyboards.keyboards import get_select_template_menu
        from bot.core.templates import get_template_manager
        
        # Форматируем сообщение (без статуса)
        message = f"🆔 <b>ID заказа:</b> #{short_id}\n\n"
        message += f"👤 <b>Покупатель:</b> {buyer}\n"
        message += f"📦 <b>Лот:</b> {lot_name}\n"
        message += f"💰 <b>Сумма:</b> {amount} ₽"
        
        # Создаём кнопки
        buttons = []
        
        # Получаем реальный UUID чата покупателя
        chat_id = await self._resolve_order_chat_id(order_data)
        
        # Проверяем количество быстрых ответов
        template_manager = get_template_manager()
        templates_count = template_manager.count()

        # Первая строка: Ответить + Быстрые ответы (если есть chat_id)
        row1 = []
        if chat_id:
            # Кнопка Ответить
            reply_callback = f"r:{chat_id}"
            if len(reply_callback) <= 64:
                row1.append(
                    InlineKeyboardButton(
                        text="📝 Ответить",
                        callback_data=reply_callback
                    )
                )

            # Кнопка Быстрые ответы (показываем всегда, даже если их 0)
            tpl_text = f"📝 Быстрые ответы ({templates_count})" if templates_count > 0 else "📝 Быстрые ответы"
            tpl_callback = f"show_templates:{chat_id}"
            # Проверяем длину callback_data (лимит Telegram - 64 байта)
            if len(tpl_callback.encode('utf-8')) <= 64:
                row1.append(
                    InlineKeyboardButton(
                        text=tpl_text,
                        callback_data=tpl_callback
                    )
                )
            else:
                logger.warning(f"Callback data для быстрых ответов слишком длинный: {len(tpl_callback.encode('utf-8'))} байт (chat_id: {chat_id[:20]}...)")

        if row1:
            buttons.append(row1)
        
        # Кнопка ссылки на заказ (используем полный order_id)
        order_url = f"https://starvell.com/order/{order_id}"
        buttons.append([
            InlineKeyboardButton(
                text="🔗 Открыть заказ",
                url=order_url
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        
        await self.notify_all_admins(
            NotificationType.NEW_ORDER,
            message,
            keyboard=keyboard
        )
        
        # Вызываем хэндлеры плагинов для новых заказов
        await self._run_plugin_handlers_for_new_order(order_data)

    async def notify_lots_raised(
        self,
        game_id: int,
        time_info: str = ""
    ):
        """Уведомление о поднятии лотов"""
        message = f"⤴️ <b><i>Поднял все лоты игры</i></b> <code>ID={game_id}</code>\n"
        
        if time_info:
            # Добавляем информацию о времени в spoiler
            message += f"<tg-spoiler>{time_info}</tg-spoiler>"
        
        await self.notify_all_admins(
            NotificationType.LOT_BUMPED,
            message,
            force=False  # Используем настройку NOTIFY_LOT_BUMP
        )
    
    async def notify_lot_action(
        self,
        action: str,
        lot_id: str,
        lot_name: str,
        reason: Optional[str] = None
    ):
        """Уведомление о действии с лотом"""
        type_map = {
            'deactivated': NotificationType.LOT_DEACTIVATED,
            'restored': NotificationType.LOT_RESTORED,
            'bumped': NotificationType.LOT_BUMPED,
        }
        
        notif_type = type_map.get(action, NotificationType.INFO)
        
        message = f"<b>Лот:</b> {lot_name}\n"
        message += f"<b>ID:</b> {lot_id}\n"
        
        if reason:
            message += f"\n<b>Причина:</b> {reason}"
        
        await self.notify_all_admins(notif_type, message)
    
    async def notify_auto_delivery(
        self,
        order_id: str,
        buyer: str,
        lot_name: str,
        delivered_items: List[str],
        success: bool = True
    ):
        """Уведомление об автовыдаче"""
        if success:
            message = f"<b>Заказ #{order_id} автоматически выполнен</b>\n\n"
            message += f"<b>Покупатель:</b> {buyer}\n"
            message += f"<b>Лот:</b> {lot_name}\n"
            message += f"<b>Выдано товаров:</b> {len(delivered_items)}\n\n"
            
            if delivered_items:
                message += "<b>Товары:</b>\n"
                for i, item in enumerate(delivered_items[:5], 1):
                    message += f"{i}. {item}\n"
                if len(delivered_items) > 5:
                    message += f"... и ещё {len(delivered_items) - 5}"
        else:
            message = f"<b>❌ Ошибка автовыдачи</b>\n\n"
            message += f"<b>Заказ:</b> #{order_id}\n"
            message += f"<b>Покупатель:</b> {buyer}\n"
            message += f"<b>Лот:</b> {lot_name}"
        
        await self.notify_all_admins(
            NotificationType.AUTO_DELIVERY,
            message
        )
    
    async def notify_error(
        self,
        error_message: str,
        context: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Уведомление об ошибке"""
        message = error_message
        
        if context:
            message = f"<b>Контекст:</b> {context}\n\n{message}"
        
        await self.notify_all_admins(
            NotificationType.ERROR,
            message,
            details=details,
            force=True
        )
    
    async def notify_update_available(self, current_version: str, latest_version: str):
        """Уведомление о доступном обновлении"""
        message = (
            f"╔══════════════════════╗\n"
            f"║  <b>ДОСТУПНО ОБНОВЛЕНИЕ!</b>       ║\n"
            f"╚══════════════════════╝\n\n"
            f"📌 <b>Текущая версия:</b> <code>{current_version}</code>\n"
            f"✨ <b>Новая версия:</b> <code>{latest_version}</code>\n\n"
            f"⬇️ При запуске обнаружена новая версия Starvell Cardinal.\n"
            f"Нажмите кнопку ниже, чтобы скачать и установить обновление.\n\n"
            f"Или используйте команду <code>/update</code>."
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить сейчас",
                    callback_data="update_now"
                )
            ]
        ])
        
        await self.notify_all_admins(
            NotificationType.UPDATE_AVAILABLE,
            message,
            keyboard=keyboard,
            force=True
        )
    
    async def _run_plugin_handlers_for_new_order(self, order_data: dict):
        """Вызов хэндлеров плагинов для новых заказов"""
        if not self.plugin_manager or not order_data:
            return
        
        # Подготавливаем данные для плагинов
        plugin_order_data = {
            'id': str(order_data.get('id', '')),
            'buyer': '',
            'amount': 0.0,
            'lot_name': '',
            'lot_description': '',
            'status': order_data.get('status', 'CREATED'),
            'chat_id': ''  # Добавляем chat_id покупателя
        }
        
        # Получаем имя покупателя
        buyer = order_data.get("user") or order_data.get("buyer") or {}
        plugin_order_data['chat_id'] = await self._resolve_order_chat_id(order_data)
        
        if isinstance(buyer, dict):
            plugin_order_data['buyer'] = (
                buyer.get("username") or 
                buyer.get("nickname") or 
                buyer.get("name") or 
                buyer.get("displayName") or
                str(buyer.get("id", "Unknown"))
            )
        elif isinstance(buyer, str):
            plugin_order_data['buyer'] = buyer
        
        # Получаем цену (конвертируем из копеек)
        amount_kopecks = (
            order_data.get("totalPrice") or 
            order_data.get("basePrice") or 
            order_data.get("price") or 
            order_data.get("amount") or 
            0
        )
        plugin_order_data['amount'] = safe_float(amount_kopecks) / 100
        
        # Получаем данные лота
        lot = order_data.get("offerDetails") or order_data.get("listing") or {}
        if isinstance(lot, dict):
            descriptions = lot.get("descriptions", {})
            if descriptions:
                rus_desc = descriptions.get("rus", {})
                plugin_order_data['lot_name'] = (
                    rus_desc.get("briefDescription") or 
                    rus_desc.get("description") or
                    lot.get("name") or 
                    "Неизвестно"
                )
                plugin_order_data['lot_description'] = rus_desc.get("description", "")
            else:
                plugin_order_data['lot_name'] = lot.get("name") or "Неизвестно"
                plugin_order_data['lot_description'] = lot.get("description", "")
        
        # Вызываем хэндлеры плагинов асинхронно
        import asyncio
        for handler in self.plugin_manager.new_order_handlers:
            try:
                # Проверяем, включён ли плагин
                plugin_uuid = getattr(handler, 'plugin_uuid', None)
                if plugin_uuid and plugin_uuid in self.plugin_manager.plugins:
                    if not self.plugin_manager.plugins[plugin_uuid].enabled:
                        continue
                
                # Вызываем асинхронный хэндлер с передачей starvell_service и bot
                if asyncio.iscoroutinefunction(handler):
                    await handler(plugin_order_data, starvell_service=self.starvell_service, bot=self.bot)
                else:
                    handler(plugin_order_data, starvell_service=self.starvell_service, bot=self.bot)
            except Exception as e:
                logger.error(f"Ошибка выполнения хэндлера плагина {handler.__name__}: {e}", exc_info=True)
    
    async def _run_plugin_handlers_for_new_message(self, chat_id: str, author: str, content: str, message_id: Optional[str] = None):
        """Вызов хэндлеров плагинов для новых сообщений"""
        if not self.plugin_manager:
            return

        logger.debug(f"Вызов плагинов для сообщения: chat_id={chat_id}, author={author}, content={content[:50]}")

        # Подготавливаем данные для плагинов
        plugin_message_data = {
            'chat_id': chat_id,
            'author': author,
            'content': content,
            'message_id': message_id or ''
        }

        # Вызываем хэндлеры плагинов асинхронно
        import asyncio
        for handler in self.plugin_manager.new_message_handlers:
            try:
                # Проверяем, включён ли плагин
                plugin_uuid = getattr(handler, 'plugin_uuid', None)
                if plugin_uuid and plugin_uuid in self.plugin_manager.plugins:
                    if not self.plugin_manager.plugins[plugin_uuid].enabled:
                        logger.debug(f"Плагин {plugin_uuid} отключён, пропускаем")
                        continue

                logger.debug(f"Вызов обработчика {handler.__name__} из плагина {plugin_uuid}")

                # Вызываем асинхронный хэндлер с передачей starvell_service и bot
                if asyncio.iscoroutinefunction(handler):
                    await handler(plugin_message_data, starvell_service=self.starvell_service, bot=self.bot)
                else:
                    handler(plugin_message_data, starvell_service=self.starvell_service, bot=self.bot)
            except Exception as e:
                logger.error(f"Ошибка выполнения хэндлера плагина {handler.__name__}: {e}", exc_info=True)


# Singleton instance
_notification_manager: Optional[NotificationManager] = None


def init_notifications(bot: Bot, starvell_service=None) -> NotificationManager:
    """Инициализировать менеджер уведомлений"""
    global _notification_manager
    _notification_manager = NotificationManager(bot, starvell_service)
    return _notification_manager


def get_notification_manager() -> Optional[NotificationManager]:
    """Получить instance менеджера уведомлений"""
    return _notification_manager
