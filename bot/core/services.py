"""
Сервис для работы со Starvell API
"""

import asyncio
from typing import Optional, List, Dict, Any
from api import StarAPI, StarAPIError
from bot.core.config import BotConfig
from bot.core.storage import Database


class StarvellService:
    """Сервис для работы с Starvell"""
    
    def __init__(self, db: Database):
        self.db = db
        self.api: Optional[StarAPI] = None
        self._lock = asyncio.Lock()
        self._session_error_notified = False  # Флаг для уведомления об ошибке сессии (1 раз)
        self.last_user_info: Dict[str, Any] = {}
        
    async def start(self):
        """Запустить сервис"""
        self.api = StarAPI(
            session_cookie=BotConfig.STARVELL_SESSION(),
            user_agent=BotConfig.USER_AGENT()
        )
        await self.api.session.start()
        # Сбрасываем флаг при старте/перезапуске
        # self._session_error_notified = False  # Закомментировано - уведомление только 1 раз за всё время
        
    async def stop(self):
        """Остановить сервис"""
        if self.api:
            await self.api.close()
    
    async def _notify_session_error(self):
        """Отправить уведомление об ошибке сессии (только один раз)"""
        if self._session_error_notified:
            return
        
        self._session_error_notified = True
        
        import logging
        logger = logging.getLogger(__name__)
        logger.error("⚠️ СЕССИЯ STARVELL УСТАРЕЛА! Токен невалиден или истёк. Обновите session_cookie в конфигурации.")
        
        # Пытаемся отправить уведомление админам
        try:
            from bot.core.notifications import get_notification_manager
            notification_manager = get_notification_manager()
            if notification_manager:
                await notification_manager.notify_all_admins(
                    "error",
                    "⚠️ <b>Сессия Starvell устарела!</b>\n\n"
                    "Токен (session_cookie) невалиден или истёк.\n"
                    "Starvell сбросил сессию.\n\n"
                    "🔧 <b>Необходимо:</b>\n"
                    "1. Получить новый session_cookie из браузера\n"
                    "2. Обновить его в конфигурации (_main.cfg)\n"
                    "3. Перезапустить бота",
                    force=True
                )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление об ошибке сессии: {e}")
            
    async def get_user_info(self) -> Dict[str, Any]:
        """Получить информацию о пользователе"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
        
        try:
            info = await self.api.get_user_info()
            self.last_user_info = info
            return info
        except Exception as e:
            from api.exceptions import NotFoundError
            # Отключено: NotFoundError не всегда означает истёкшую сессию
            # if isinstance(e, NotFoundError):
            #     await self._notify_session_error()
            raise
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить профиль пользователя по ID
        
        Args:
            user_id: ID пользователя в Starvell
            
        Returns:
            dict: Данные профиля (nickname, name, id и др.) или None если не найден
        """
        if not self.api:
            raise RuntimeError("API не инициализирован")
        return await self.api.get_user_profile(user_id)
        
    async def get_chats(self) -> List[Dict[str, Any]]:
        """Получить список чатов"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
        
        try:
            data = await self.api.get_chats()
            return data.get("pageProps", {}).get("chats", [])
        except Exception as e:
            from api.exceptions import NotFoundError
            # Отключено: NotFoundError не всегда означает истёкшую сессию
            # if isinstance(e, NotFoundError):
            #     await self._notify_session_error()
            raise
        
    async def get_unread_chats(self) -> List[Dict[str, Any]]:
        """Получить чаты с непрочитанными сообщениями"""
        chats = await self.get_chats()
        return [chat for chat in chats if (chat.get("unreadMessageCount") or chat.get("unreadCount") or 0) > 0]
        
    async def get_messages(self, chat_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить сообщения из чата"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
        
        try:
            return await self.api.get_messages(chat_id, limit)
        except Exception as e:
            from api.exceptions import NotFoundError
            # Отключено: NotFoundError не всегда означает истёкшую сессию
            # if isinstance(e, NotFoundError):
            #     await self._notify_session_error()
            raise
        
    async def send_message(self, chat_id: str, content: str) -> Dict[str, Any]:
        """Отправить сообщение в чат"""
        if not self.api:
            raise RuntimeError("API не инициализирован")

        # Добавляем вотермарк в сообщение при отправке в Starvell, если включено
        try:
            from bot.core.config import BotConfig
            if BotConfig.USE_WATERMARK():
                wm = BotConfig.WATERMARK() or ''
                if wm:
                    # Добавляем в начало, затем пустая строка и оригинальное сообщение
                    content = f"{wm}\n\n{content}"
        except Exception:
            # Не критично — продолжаем без вотермарки
            pass

        # Выполняем сетевой запрос БЕЗ lock
        result = await self.api.send_message(chat_id, content)

        # Только запись в БД под lock
        async with self._lock:
            await self.db.add_sent_message(chat_id, content)

        return result
    
    async def mark_chat_as_read(self, chat_id: str) -> bool:
        """Пометить чат как прочитанный"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
        return await self.api.mark_chat_as_read(chat_id)
    
    async def find_chat_by_user_id(self, user_id: str) -> Optional[str]:
        """Найти ID чата с конкретным пользователем"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
        return await self.api.find_chat_by_user_id(user_id)
            
    async def get_orders(self) -> List[Dict[str, Any]]:
        """Получить список заказов"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
        
        try:
            # Используем новый метод для получения ВСЕХ заказов
            orders = await self.api.get_all_orders()
            return orders if orders else []
        except Exception as e:
            # Проверяем, является ли это ошибкой NotFound (обычно устаревшая сессия)
            from api.exceptions import NotFoundError
            # Отключено: NotFoundError не всегда означает истёкшую сессию
            # if isinstance(e, NotFoundError):
            #     await self._notify_session_error()
            raise
    
    async def get_all_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получить ВСЕ заказы с опциональным фильтром по статусу
        
        Args:
            status: Фильтр по статусу ("CREATED", "COMPLETED", "REFUND", "PRE_CREATED")
                   Если None - возвращает все заказы
        
        Returns:
            list: Список всех заказов
        """
        if not self.api:
            raise RuntimeError("API не инициализирован")
        
        try:
            orders = await self.api.get_all_orders(status=status)
            return orders if orders else []
        except Exception as e:
            from api.exceptions import NotFoundError
            # Отключено: NotFoundError не всегда означает истёкшую сессию
            # if isinstance(e, NotFoundError):
            #     await self._notify_session_error()
            raise
        
    async def refund_order(self, order_id: str) -> Dict[str, Any]:
        """Вернуть деньги за заказ"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
        return await self.api.refund_order(order_id)
        
    async def confirm_order(self, order_id: str) -> Dict[str, Any]:
        """Подтвердить заказ"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
        return await self.api.confirm_order(order_id)
    
    async def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """Получить детальную информацию о заказе"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
        return await self.api.get_order_details(order_id)
        
    async def bump_offers(
        self,
        game_id: Optional[int] = None,
        category_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Поднять офферы в топ"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
            
        # Используем значения из конфига, если не переданы
        game_id = game_id or BotConfig.AUTO_BUMP_GAME_ID()
        category_ids = category_ids or BotConfig.AUTO_BUMP_CATEGORIES()
        
        async with self._lock:
            try:
                # Сначала получаем user_info для SID
                await self.api.get_user_info()
                
                # Поднимаем
                result = await self.api.bump_offers(game_id, category_ids)
                
                # Сохраняем в БД
                await self.db.add_bump_history(game_id, category_ids, True)
                
                return result
            except Exception as e:
                from api.exceptions import NotFoundError
                # Отключено: NotFoundError не всегда означает истёкшую сессию
                # if isinstance(e, NotFoundError):
                #     await self._notify_session_error()
                await self.db.add_bump_history(game_id, category_ids, False)
                raise
                
    async def get_new_messages_count(self) -> int:
        """Получить количество новых сообщений"""
        chats = await self.get_unread_chats()
        return sum((chat.get("unreadMessageCount") or chat.get("unreadCount") or 0) for chat in chats)
        
    async def check_new_messages(self) -> List[Dict[str, Any]]:
        """
        Проверить новые сообщения
        
        ОПТИМИЗИРОВАНО: проверяем только чаты с непрочитанными сообщениями
        вместо всех чатов, чтобы снизить количество API запросов.
        """
        import logging
        from bot.core.config import BotConfig
        logger = logging.getLogger(__name__)

        def message_sort_key(message: Dict[str, Any]) -> str:
            for key in ("createdAt", "created_at", "timestamp", "sentAt", "updatedAt", "date", "id"):
                value = message.get(key)
                if value is not None:
                    return str(value)
            return ""

        def get_chat_messages(chat: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
            messages = chat.get("messages", [])
            if not isinstance(messages, list):
                return []
            return sorted(messages, key=message_sort_key, reverse=True)[:limit]
        
        new_messages = []

        my_user_id = str((self.last_user_info.get("user") or {}).get("id", ""))
        if not my_user_id:
            try:
                user_info = await self.get_user_info()
                my_user_id = str((user_info.get("user") or {}).get("id", ""))
            except Exception:
                my_user_id = ""
        
        # Получаем все чаты
        chats = await self.get_chats()
        
        # ОПТИМИЗАЦИЯ: фильтруем только чаты с непрочитанными сообщениями
        unread_chats = [c for c in chats if (c.get("unreadMessageCount") or c.get("unreadCount") or 0) > 0]
        
        logger.debug(f"📬 Всего чатов: {len(chats)}, с непрочитанными: {len(unread_chats)}")
        
        # Проверяем настройку авто-прочтения
        auto_read_enabled = BotConfig.AUTO_READ_ENABLED()
        
        for chat in chats:
            chat_id = chat.get("id")
            if not chat_id:
                continue
            
            chat_new_messages = []
            
            # Получаем последнее известное сообщение из БД
            last_known_id = await self.db.get_last_message(chat_id)
            unread_count = chat.get("unreadMessageCount") or chat.get("unreadCount") or 0
            
            # Получаем последние 10 сообщений чата
            messages = get_chat_messages(chat, limit=10)
            
            if not messages:
                continue

            latest_id = messages[0].get("id")
            has_latest_change = bool(latest_id and latest_id != last_known_id)
            
            # Если это первый раз (нет в БД), определяем непрочитанные
            if not last_known_id:
                if latest_id:
                    await self.db.set_last_message(chat_id, latest_id)

                if unread_count <= 0:
                    continue

                if unread_count > 0:
                    # В новом чате выбираем именно входящие сообщения покупателя.
                    incoming_messages = messages
                    if my_user_id:
                        incoming_messages = [
                            msg for msg in messages
                            if str(msg.get("authorId", "")) != my_user_id
                        ]

                    if not incoming_messages:
                        incoming_messages = messages

                    for msg in incoming_messages[:min(unread_count, len(incoming_messages))]:
                        chat_new_messages.append({
                            "chat_id": chat_id,
                            "message": msg,
                            "chat": chat,
                        })
                    logger.debug(f"🆕 Обнаружено {len(chat_new_messages)} нов. сообщений в новом чате {chat_id}")
                
                # Сохраняем ID последнего сообщения
                
                if chat_new_messages:
                    new_messages.extend(chat_new_messages)
                    if auto_read_enabled:
                        await self.mark_chat_as_read(chat_id)
                continue

            if not has_latest_change and unread_count <= 0:
                continue

            if has_latest_change and unread_count <= 0:
                logger.debug(
                    f"рџ”Ѓ РћР±РЅР°СЂСѓР¶РµРЅРѕ РёР·РјРµРЅРµРЅРёРµ latest message РІ С‡Р°С‚Рµ {chat_id} "
                    f"Р±РµР· unreadCount (last_known_id={last_known_id}, latest_id={latest_id})"
                )

            for msg in messages:
                msg_id = msg.get("id")
                
                if msg_id == last_known_id:
                    break
                    
                # Это новое сообщение
                chat_new_messages.append({
                    "chat_id": chat_id,
                    "message": msg,
                    "chat": chat,
                })
            
            # Добавляем в общий список
            new_messages.extend(chat_new_messages)
                    
            # Обновляем последнее сообщение
            if latest_id:
                await self.db.set_last_message(chat_id, latest_id)
            
            # Помечаем чат как прочитанный после обработки (если включено)
            if auto_read_enabled and (unread_count > 0 or chat_new_messages):
                await self.mark_chat_as_read(chat_id)
                    
        return new_messages
        
    async def check_new_orders(self) -> List[Dict[str, Any]]:
        """Проверить новые заказы"""
        new_orders = []
        
        orders = await self.get_orders()
        
        for order in orders:
            order_id = order.get("id")
            status = order.get("status")
            
            if not order_id:
                continue
                
            # Проверяем, знаем ли мы этот заказ
            last_known = await self.db.get_last_order(order_id)
            
            if not last_known:
                # Новый заказ
                new_orders.append(order)
                await self.db.set_last_order(order_id, status)
            elif last_known["status"] != status:
                # Статус изменился
                new_orders.append(order)
                await self.db.set_last_order(order_id, status)
                
        return new_orders
    
    async def get_lots(self) -> List[Dict[str, Any]]:
        """Получить список лотов пользователя"""
        if not self.api:
            raise RuntimeError("API не инициализирован")
        
        try:
            # Получаем информацию о текущем пользователе
            user_info = await self.api.get_user_info()
            user = user_info.get("user")
            
            if not user or not user.get("id"):
                raise RuntimeError("Не удалось получить ID пользователя")
            
            user_id = user.get("id")
            
            # Получаем офферы этого пользователя
            offers = await self.api.get_user_offers(user_id)
            return offers
        except Exception as e:
            from api.exceptions import NotFoundError
            # Отключено: NotFoundError не всегда означает истёкшую сессию
            # if isinstance(e, NotFoundError):
            #     await self._notify_session_error()
            raise RuntimeError(f"Ошибка получения лотов: {e}")
    
    async def activate_lot(self, lot_id: str, amount: Optional[int] = None) -> bool:
        """
        Активировать лот с указанным количеством
        
        Args:
            lot_id: ID лота
            amount: Количество товара (опционально)
        
        Returns:
            True если успешно, False otherwise
        """
        if not self.api:
            raise RuntimeError("API не инициализирован")
        
        try:
            # TODO: Реализовать активацию через API Starvell
            # result = await self.api.activate_lot(lot_id, amount)
            # Пока возвращаем заглушку
            return True
        except Exception as e:
            raise RuntimeError(f"Ошибка активации лота {lot_id}: {e}")
    
    async def keep_alive(self) -> bool:
        """
        Поддержка онлайн статуса
        
        Returns:
            True если успешно
        """
        if not self.api:
            raise RuntimeError("API не инициализирован")
        
        return await self.api.keep_alive()

    async def connect_online_socket(self):
        """Открыть websocket /online для поддержания онлайн-статуса."""
        if not self.api:
            raise RuntimeError("API не инициализирован")

        return await self.api.connect_online_socket()
    
    async def raise_lots(self, game_id: int, category_ids: List[int]) -> bool:
        """
        Поднять лоты категорий
        
        Args:
            game_id: ID игры
            category_ids: Список ID категорий
        
        Returns:
            True если успешно, False otherwise
        """
        if not self.api:
            raise RuntimeError("API не инициализирован")
        
        try:
            async with self._lock:
                # Используем существующий метод bump_offers
                result = await self.bump_offers(game_id, category_ids)
                return result.get('success', False)
        except Exception as e:
            # Пробрасываем исключение дальше для обработки wait time
            raise RuntimeError(f"Ошибка поднятия лотов: {e}")

    # ==================== Методы для автодемпера ====================

    async def get_my_lots(self) -> List[Dict[str, Any]]:
        """
        Получить список своих активных лотов

        Returns:
            list: Список активных лотов с полями:
                - id: ID лота
                - title: Название
                - price: Цена
                - gameId: ID игры
                - categoryId: ID категории
                - active: Активен ли лот
        """
        try:
            lots = await self.get_lots()
            # Фильтруем только активные
            active_lots = [lot for lot in lots if lot.get("active", False)]
            return active_lots
        except Exception as e:
            logger.error(f"Ошибка получения своих лотов: {e}")
            return []

    async def get_competitors(self, game_id: int, category_id: int) -> List[Dict[str, Any]]:
        """
        Получить список конкурентов в категории

        Args:
            game_id: ID игры
            category_id: ID категории

        Returns:
            list: Список лотов конкурентов с полями:
                - id: ID лота
                - price: Цена
                - userId: ID продавца
                - sellerName: Имя продавца
                - sellerReviews: Количество отзывов
                - active: Активен ли лот
        """
        if not self.api:
            raise RuntimeError("API не инициализирован")

        try:
            # Получаем свой user_id чтобы исключить свои лоты
            user_info = await self.get_user_info()
            my_user_id = user_info.get("user", {}).get("id")

            # Получаем все офферы в категории
            # TODO: Нужно реализовать метод get_category_offers в api/client.py
            # Пока возвращаем пустой список
            logger.warning("Метод get_competitors требует реализации get_category_offers в API")
            return []

            # Когда метод будет реализован:
            # all_offers = await self.api.get_category_offers(game_id, category_id)
            #
            # # Фильтруем конкурентов (не наши лоты, активные)
            # competitors = [
            #     offer for offer in all_offers
            #     if offer.get("userId") != my_user_id
            #     and offer.get("active", False)
            # ]
            #
            # return competitors

        except Exception as e:
            logger.error(f"Ошибка получения конкурентов: {e}")
            return []

    async def update_lot_price(self, lot_id: int, new_price: float) -> Dict[str, Any]:
        """
        Обновить цену лота

        Args:
            lot_id: ID лота
            new_price: Новая цена в рублях

        Returns:
            dict: Результат операции с полем success
        """
        if not self.api:
            raise RuntimeError("API не инициализирован")

        try:
            # TODO: Нужно реализовать метод update_offer_price в api/client.py
            # Пока возвращаем заглушку
            logger.warning("Метод update_lot_price требует реализации update_offer_price в API")
            return {"success": False, "error": "Метод не реализован"}

            # Когда метод будет реализован:
            # result = await self.api.update_offer_price(lot_id, new_price)
            # return result

        except Exception as e:
            logger.error(f"Ошибка обновления цены лота {lot_id}: {e}")
            return {"success": False, "error": str(e)}
