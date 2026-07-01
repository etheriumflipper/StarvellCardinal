"""Основной клиент API"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from .config import Config
from .session import SessionManager
from .utils import BuildIdCache, extract_build_id, extract_next_data
from .exceptions import NotFoundError, ForbiddenError, StarAPIError

logger = logging.getLogger("API")

_CATEGORIES_CACHE_FILE = Path("storage/cache/auto_raise_categories.json")


class StarAPI:
    """
    Главный класс для работы с Starvell API
    
    Пример использования:
        async with StarAPI(session_cookie="your_cookie") as api:
            user = await api.get_user_info()
            chats = await api.get_chats()
    """
    
    def __init__(
        self,
        session_cookie: str,
        user_agent: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        """
        Инициализация клиента
        
        Args:
            session_cookie: Cookie сессии пользователя
            user_agent: Кастомный User-Agent (опционально)
            timeout: Таймаут запросов в секундах (опционально)
        """
        self.config = Config(user_agent=user_agent, timeout=timeout)
        self.session = SessionManager(session_cookie, self.config)
        self._build_id_cache = BuildIdCache(ttl=self.config.BUILD_ID_CACHE_TTL)
        self._socket_io_available: Optional[bool] = None
        
    async def __aenter__(self):
        await self.session.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()
        
    async def close(self):
        """Закрыть сессию"""
        await self.session.close()
        
    # ==================== Внутренние методы ====================
    
    async def _get_build_id(self) -> str:
        """Получить build_id (с кэшированием)"""
        async def fetch():
            html = await self.session.get_text(
                f"{self.config.BASE_URL}/",
                headers={"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
            )
            return extract_build_id(html)
            
        return await self._build_id_cache.get(fetch)
        
    async def _get_next_data(
        self,
        path: str,
        params: Optional[str] = None,
        include_sid: bool = False,
        referer: Optional[str] = None,
    ) -> dict:
        """
        Получить данные из Next.js Data API
        
        Args:
            path: Путь (например, "index.json" или "chat.json")
            params: Query параметры (например, "?offer_id=123")
            include_sid: Включить SID cookie в запрос
            referer: Referer для запроса
        """
        for attempt in range(2):
            try:
                build_id = await self._get_build_id()
                url = f"{self.config.BASE_URL}/_next/data/{build_id}/{path}"
                
                if params:
                    url += params
                    
                data = await self.session.get_json(
                    url,
                    referer=referer or f"{self.config.BASE_URL}/",
                    headers={"x-nextjs-data": "1"},
                    include_sid=include_sid,
                )
                
                return data
                
            except NotFoundError:
                if attempt == 0:
                    # Build ID устарел, сбрасываем кэш
                    self._build_id_cache.reset()
                    continue
                raise
                
        raise RuntimeError("Не удалось получить Next.js данные")

    async def _get_user_page_props(self, user_id: int) -> dict:
        """
        Получить pageProps профиля пользователя.
        Starvell/Qrator может резать отдельные пути — пробуем несколько вариантов.
        """
        if not self.session.get_sid():
            try:
                await self.get_user_info()
            except Exception as sid_error:
                logger.debug(f"Не удалось обновить SID перед профилем: {sid_error}")

        referer = f"{self.config.BASE_URL}/users/{user_id}"
        attempts: List[Tuple[str, Optional[str]]] = [
            (f"users/{user_id}.json", f"?user_id={user_id}"),
            (f"user/{user_id}.json", f"?user_id={user_id}"),
            (f"user/{user_id}.json", None),
            ("account/offers.json", None),
            ("account/sells.json", None),
        ]

        last_error: Optional[Exception] = None
        for path, params in attempts:
            try:
                data = await self._get_next_data(
                    path,
                    params=params,
                    include_sid=True,
                    referer=referer,
                )
                page_props = data.get("pageProps", {})
                if self._extract_user_categories(page_props) or page_props.get("userProfileOffers"):
                    return page_props
            except ForbiddenError as exc:
                last_error = exc
                logger.debug(f"Профиль через {path} заблокирован (403)")
            except NotFoundError as exc:
                last_error = exc
                logger.debug(f"Профиль через {path} не найден (404)")

        try:
            return await self._get_user_page_props_html(user_id)
        except Exception as exc:
            last_error = exc
            logger.debug(f"HTML профиля недоступен: {exc}")

        if last_error:
            raise last_error
        raise ForbiddenError(f"Не удалось получить профиль пользователя {user_id}")

    async def _get_user_page_props_html(self, user_id: int) -> dict:
        """Fallback: парсинг __NEXT_DATA__ со страницы /users/{id}."""
        html = await self.session.get_text(
            f"{self.config.BASE_URL}/users/{user_id}",
            referer=f"{self.config.BASE_URL}/",
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "cache-control": "max-age=0",
                "upgrade-insecure-requests": "1",
            },
            include_sid=True,
        )
        data = extract_next_data(html)
        return data.get("props", {}).get("pageProps", data.get("pageProps", {}))

    def _load_categories_cache(self, user_id: int) -> Dict[int, List[int]]:
        try:
            if not _CATEGORIES_CACHE_FILE.exists():
                return {}
            payload = json.loads(_CATEGORIES_CACHE_FILE.read_text(encoding="utf-8"))
            if str(payload.get("user_id")) != str(user_id):
                return {}
            cached = payload.get("game_categories") or {}
            result: Dict[int, List[int]] = {}
            for game_id, categories in cached.items():
                gid = int(game_id)
                result[gid] = [int(c) for c in categories]
            return result
        except Exception as exc:
            logger.debug(f"Не удалось прочитать кэш категорий: {exc}")
            return {}

    def _save_categories_cache(self, user_id: int, game_categories: Dict[int, List[int]]) -> None:
        try:
            _CATEGORIES_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "user_id": user_id,
                "game_categories": {str(k): v for k, v in game_categories.items()},
            }
            _CATEGORIES_CACHE_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug(f"Не удалось сохранить кэш категорий: {exc}")

    async def _categories_from_orders(self) -> Dict[int, List[int]]:
        """Собрать game/category из истории заказов (REST API обычно не режется)."""
        game_categories: Dict[int, List[int]] = {}
        try:
            orders = await self.get_all_orders()
        except Exception as exc:
            logger.debug(f"Не удалось получить заказы для fallback категорий: {exc}")
            return game_categories

        for order in orders:
            details = order.get("offerDetails") or {}
            game = details.get("game") or {}
            category = details.get("category") or {}
            game_id = game.get("id") or details.get("gameId") or order.get("gameId")
            category_id = category.get("id") or details.get("categoryId") or order.get("categoryId")
            if game_id and category_id:
                game_categories.setdefault(int(game_id), [])
                cid = int(category_id)
                if cid not in game_categories[int(game_id)]:
                    game_categories[int(game_id)].append(cid)
        return game_categories

    async def _categories_from_offer_ids(self, offer_ids: List[int]) -> Dict[int, List[int]]:
        """Детали каждого лота через /offers/{id}.json — обход блокировки профиля."""
        game_categories: Dict[int, List[int]] = {}
        unique_ids = []
        seen = set()
        for offer_id in offer_ids:
            if offer_id and offer_id not in seen:
                seen.add(offer_id)
                unique_ids.append(int(offer_id))

        for offer_id in unique_ids[:40]:
            try:
                data = await self.get_offer(offer_id)
                page_props = data.get("pageProps", {})
                offer = page_props.get("offer") or {}
                game_id = offer.get("gameId") or (offer.get("game") or {}).get("id")
                category_id = offer.get("categoryId") or (offer.get("category") or {}).get("id")
                if game_id and category_id:
                    game_categories.setdefault(int(game_id), [])
                    cid = int(category_id)
                    if cid not in game_categories[int(game_id)]:
                        game_categories[int(game_id)].append(cid)
            except Exception as exc:
                logger.debug(f"Не удалось получить offer {offer_id}: {exc}")
            await asyncio.sleep(0.05)
        return game_categories

    async def _discover_offer_ids(self) -> List[int]:
        """Собрать ID лотов из заказов для fallback."""
        offer_ids: List[int] = []
        seen = set()
        try:
            orders = await self.get_all_orders()
            for order in orders:
                for key in ("offerId", "offer_id"):
                    oid = order.get(key)
                    if oid and oid not in seen:
                        seen.add(oid)
                        offer_ids.append(int(oid))
        except Exception as exc:
            logger.debug(f"discover_offer_ids failed: {exc}")
        return offer_ids

    async def _resolve_user_categories(self, user_id: int) -> Dict[int, List[int]]:
        """Полная цепочка получения категорий для авто-поднятия."""
        try:
            page_props = await self._get_user_page_props(user_id)
            game_categories = self._extract_user_categories(page_props)
            if game_categories:
                self._save_categories_cache(user_id, game_categories)
                return game_categories
        except ForbiddenError:
            logger.warning(
                "⚠️ Профиль Starvell заблокирован антиботом — пробую fallback через заказы/кэш"
            )
        except Exception as exc:
            logger.warning(f"⚠️ Не удалось получить профиль: {exc}")

        cached = self._load_categories_cache(user_id)
        if cached:
            logger.info(f"📦 Категории из кэша: {len(cached)} игр")
            return cached

        from_orders = await self._categories_from_orders()
        if from_orders:
            logger.info(f"📦 Категории из заказов: {len(from_orders)} игр")
            self._save_categories_cache(user_id, from_orders)
            return from_orders

        offer_ids = await self._discover_offer_ids()
        if offer_ids:
            from_offers = await self._categories_from_offer_ids(offer_ids)
            if from_offers:
                logger.info(f"📦 Категории из деталей лотов: {len(from_offers)} игр")
                self._save_categories_cache(user_id, from_offers)
                return from_offers

        return {}

    def _extract_user_categories(self, page_props: dict) -> Dict[int, List[int]]:
        """Сгруппировать категории лотов пользователя по game_id."""
        categories = page_props.get("userProfileOffers")
        if not categories:
            categories = (page_props.get("bff") or {}).get("userProfileOffers")
        if not categories:
            categories = page_props.get("categoriesWithOffers") or []

        game_categories: Dict[int, List[int]] = {}
        for category in categories:
            if not isinstance(category, dict):
                continue
            game_id = category.get("gameId")
            category_id = category.get("id")
            offers = category.get("offers") or []
            if game_id and category_id and offers:
                game_categories.setdefault(game_id, [])
                if category_id not in game_categories[game_id]:
                    game_categories[game_id].append(category_id)
        return game_categories
        
    # ==================== Аутентификация ====================
    
    async def get_user_info(self) -> Dict[str, Any]:
        """
        Получить информацию о текущем пользователе
        
        Returns:
            dict: Информация о пользователе и статус авторизации
        """
        data = await self._get_next_data("index.json")
        page_props = data.get("pageProps", {})
        
        # Попытка получить SID из ответа
        sid = page_props.get("sid")
        if sid:
            self.session.set_sid(sid)
        
        return {
            "authorized": bool(page_props.get("user")),
            "user": page_props.get("user"),
            "sid": sid or self.session.get_sid(),
            "theme": page_props.get("currentTheme"),
        }
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить профиль пользователя по ID
        
        Args:
            user_id: ID пользователя в Starvell
            
        Returns:
            dict: Данные профиля (nickname, name, id и др.) или None если не найден
        """
        try:
            # Используем URL вида https://starvell.com/_next/data/{build_id}/user/{user_id}.json
            data = await self._get_next_data(f"user/{user_id}.json")
            page_props = data.get("pageProps", {})
            
            # Извлекаем данные пользователя
            user_data = page_props.get("user")
            if user_data:
                return {
                    "id": user_data.get("id"),
                    "nickname": user_data.get("nickname") or user_data.get("name"),
                    "name": user_data.get("name"),
                    "username": user_data.get("username"),
                    "avatar": user_data.get("avatar"),
                }
            
            return None
        except Exception as e:
            logger.debug(f"Не удалось получить профиль пользователя {user_id}: {e}")
            return None
        
    # ==================== Чаты ====================
    
    async def get_chats(self) -> Dict[str, Any]:
        """
        Получить список всех чатов
        
        Returns:
            dict: Данные о чатах пользователя
        """
        return await self._get_next_data("chat.json", include_sid=True)

    async def get_chat(self, chat_id: str) -> Dict[str, Any]:
        """
        Получить полные данные чата с историей сообщений.
        Пробует несколько Next.js маршрутов и REST fallback.
        """
        referer = f"{self.config.BASE_URL}/chat/{chat_id}"
        attempts = [
            (f"chat/{chat_id}.json", f"?chatId={chat_id}"),
            (f"chat/{chat_id}.json", f"?id={chat_id}"),
            (f"chats/{chat_id}.json", None),
            (f"chat/{chat_id}.json", None),
        ]
        for path, params in attempts:
            try:
                data = await self._get_next_data(
                    path,
                    params=params,
                    include_sid=True,
                    referer=referer,
                )
                page_props = data.get("pageProps", {})
                if page_props.get("messages") or page_props.get("chat"):
                    return page_props
            except Exception as exc:
                logger.debug(f"get_chat {path} не сработал: {exc}")

        rest_endpoints = [
            (f"{self.config.API_URL}/chats/{chat_id}/messages", None),
            (f"{self.config.API_URL}/messages", {"chatId": chat_id}),
            (f"{self.config.API_URL}/messages/list", {"chatId": chat_id}),
        ]
        for url, params in rest_endpoints:
            try:
                if params:
                    query = "&".join(f"{k}={v}" for k, v in params.items())
                    full_url = f"{url}?{query}"
                else:
                    full_url = url
                data = await self.session.get_json(
                    full_url,
                    referer=referer,
                    include_sid=True,
                )
                if isinstance(data, list) and data:
                    return {"messages": data, "chat": {"id": chat_id}}
                if isinstance(data, dict):
                    messages = data.get("messages") or data.get("items") or data.get("data")
                    if messages:
                        return {"messages": messages, "chat": data.get("chat") or {"id": chat_id}}
            except Exception as exc:
                logger.debug(f"get_chat REST {url} не сработал: {exc}")

        return {}
        
    async def get_messages(self, chat_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получить сообщения из чата

        Args:
            chat_id: ID чата
            limit: Максимальное количество сообщений

        Returns:
            list: Список сообщений
        """
        messages = await self.get_chat_messages(chat_id, limit=limit)
        if messages:
            return messages

        def message_sort_key(message: Dict[str, Any]) -> str:
            for key in ("createdAt", "created_at", "timestamp", "sentAt", "updatedAt", "date", "id"):
                value = message.get(key)
                if value is not None:
                    return str(value)
            return ""

        try:
            chats_data = await self.get_chats()
            for chat in chats_data.get("pageProps", {}).get("chats", []):
                if chat.get("id") == chat_id:
                    messages = chat.get("messages", [])
                    if not isinstance(messages, list):
                        return []
                    sorted_messages = sorted(messages, key=message_sort_key, reverse=True)
                    return sorted_messages[:limit]
            return []
        except Exception as e:
            logger.error(f"Ошибка получения сообщений для чата {chat_id}: {e}")
            return []

    async def get_chat_messages(self, chat_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить историю сообщений чата (с загрузкой полной страницы чата)."""
        def message_sort_key(message: Dict[str, Any]) -> str:
            for key in ("createdAt", "created_at", "timestamp", "sentAt", "updatedAt", "date", "id"):
                value = message.get(key)
                if value is not None:
                    return str(value)
            return ""

        page_props = await self.get_chat(chat_id)
        messages = page_props.get("messages") or []
        chat_obj = page_props.get("chat") or {}
        if not messages and isinstance(chat_obj, dict):
            messages = chat_obj.get("messages") or []

        if not isinstance(messages, list):
            return []

        sorted_messages = sorted(messages, key=message_sort_key, reverse=True)
        return sorted_messages[:limit]
        
    async def send_message(self, chat_id: str, content: str) -> Dict[str, Any]:
        """
        Отправить сообщение в чат
        
        Args:
            chat_id: ID чата
            content: Текст сообщения
            
        Returns:
            dict: Информация об отправленном сообщении
        """
        return await self.session.post_json(
            f"{self.config.API_URL}/messages/send",
            data={"chatId": chat_id, "content": content},
            referer=f"{self.config.BASE_URL}/chat/{chat_id}",
        )
    
    async def mark_chat_as_read(self, chat_id: str) -> bool:
        """
        Пометить чат как прочитанный
        
        Args:
            chat_id: ID чата
            
        Returns:
            bool: True если успешно
        """
        try:
            if not self.session.get_sid():
                try:
                    await self.get_user_info()
                except Exception as e:
                    logger.debug(f"Не удалось получить SID перед автопрочтением чата {chat_id}: {e}")

            # Пробуем разные возможные эндпоинты
            endpoints = [
                f"{self.config.API_URL}/messages/read",
                f"{self.config.API_URL}/chats/read", 
                f"{self.config.API_URL}/chat/read",
            ]

            payloads = [
                {"chatId": chat_id},
                {"chat_id": chat_id},
                {"id": chat_id},
            ]

            last_error = None
            for endpoint in endpoints:
                for payload in payloads:
                    try:
                        await self.session.post_json(
                            endpoint,
                            data=payload,
                            referer=f"{self.config.BASE_URL}/chat/{chat_id}",
                            include_sid=True,
                        )
                        logger.debug(
                            f"Чат {chat_id} помечен прочитанным через {endpoint} с payload {list(payload.keys())[0]}"
                        )
                        return True
                    except Exception as e:
                        last_error = e
                        logger.debug(
                            f"Не сработало автопрочтение чата {chat_id}: endpoint={endpoint}, "
                            f"payload={payload}, error={e}"
                        )

            logger.warning(
                f"Не удалось автоматически пометить чат {chat_id} как прочитанный: "
                f"{last_error or 'неизвестная ошибка'}"
            )
            try:
                await self.get_messages(chat_id, limit=1)
                logger.debug(f"Чат {chat_id} помечен прочитанным через fallback get_messages()")
                return True
            except Exception as fallback_error:
                logger.warning(
                    f"Fallback автопрочтения для чата {chat_id} тоже не сработал: {fallback_error}"
                )
                return False

        except Exception as e:
            logger.debug(f"Не удалось пометить чат {chat_id} как прочитанный: {e}")
            return False
    
    async def find_chat_by_user_id(self, user_id: str) -> Optional[str]:
        """
        Найти ID чата с конкретным пользователем
        
        Args:
            user_id: ID пользователя для поиска
            
        Returns:
            str | None: ID чата если найден, иначе None
        """
        try:
            chats_data = await self.get_chats()
            chats = chats_data.get("pageProps", {}).get("chats", [])
            
            for chat in chats:
                # Проверяем companion (для личных чатов)
                companion = chat.get("companion", {})
                if companion and str(companion.get("id")) == str(user_id):
                    return chat.get("id")
                
                # Проверяем members (для групповых чатов)
                members = chat.get("members", [])
                for member in members:
                    if str(member.get("id")) == str(user_id):
                        return chat.get("id")
            
            return None
        except Exception as e:
            logger.error(f"Ошибка поиска чата для пользователя {user_id}: {e}")
            return None
        
    # ==================== Заказы ====================
    
    async def get_sells(self) -> Dict[str, Any]:
        """
        Получить список продаж (только первые 20 через Next.js Data API)
        
        ⚠️ DEPRECATED: Используйте get_all_orders() для получения ВСЕХ заказов
        
        Returns:
            dict: Данные о продажах (ограничено 20 заказами)
        """
        return await self._get_next_data("account/sells.json")
    
    async def get_all_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получить ВСЕ заказы с информацией о покупателях
        
        Использует гибридный подход
        
        Args:
            status: Фильтр по статусу ("CREATED", "COMPLETED", "REFUND", "PRE_CREATED")
                   Если None - возвращает все заказы
        
        Returns:
            list: Список всех заказов с информацией о покупателях
        """
        payload = {"filter": {}}
        if status:
            payload["filter"]["status"] = status
        
        all_orders = await self.session.post_json(
            f"{self.config.API_URL}/orders/list",
            data=payload,
            referer=f"{self.config.BASE_URL}/account/sells",
        )
        
        if not isinstance(all_orders, list):
            all_orders = []
        
        try:
            data = await self._get_next_data("account/sells.json")
            page_props = data.get("pageProps", {})
            recent_orders = page_props.get("orders", [])
            
            user_map = {}
            for order in recent_orders:
                order_id = order.get("id")
                user = order.get("user")
                if order_id and user:
                    user_map[order_id] = user
            
            for order in all_orders:
                order_id = order.get("id")
                if order_id in user_map:
                    order["user"] = user_map[order_id]
        
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Не удалось обогатить заказы данными пользователей: {e}")
        
        return all_orders
        
    async def refund_order(self, order_id: str) -> Dict[str, Any]:
        """
        Вернуть деньги за заказ
        
        Args:
            order_id: ID заказа
            
        Returns:
            dict: Результат операции
        """
        return await self.session.post_json(
            f"{self.config.API_URL}/orders/refund",
            data={"orderId": order_id},
            referer=f"{self.config.BASE_URL}/order/{order_id}",
            include_sid=True,
        )
        
    async def confirm_order(self, order_id: str) -> Dict[str, Any]:
        """
        Подтвердить заказ
        
        Args:
            order_id: ID заказа
            
        Returns:
            dict: Результат операции
        """
        return await self.session.post_json(
            f"{self.config.API_URL}/orders/confirm",
            data={"orderId": order_id},
            referer=f"{self.config.BASE_URL}/order/{order_id}",
            include_sid=True,
        )
    
    async def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """
        Получить детальную информацию о заказе
        
        Args:
            order_id: ID заказа (например, 019b95a8-df7d-683c-17a9-3889985947d6)
            
        Returns:
            dict: Полные данные заказа включая chat_id, buyer, lot и т.д.
        """
        return await self._get_next_data(
            f"order/{order_id}.json",
            params=f"?order_id={order_id}",
            include_sid=True,
        )
        
    # ==================== Офферы ====================
    
    async def get_offer(self, offer_id: int) -> Dict[str, Any]:
        """
        Получить детальную информацию об оффере
        
        Args:
            offer_id: ID оффера
            
        Returns:
            dict: Данные об оффере
        """
        return await self._get_next_data(
            f"offers/{offer_id}.json",
            params=f"?offer_id={offer_id}",
            include_sid=True,
        )
        
    async def bump_offers(
        self,
        game_id: int,
        category_ids: List[int],
        referer: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Поднять офферы в топ (bump)
        
        Args:
            game_id: ID игры
            category_ids: Список ID категорий для поднятия
            referer: Referer для запроса (опционально)
            
        Returns:
            dict: Результат операции с деталями запроса
        """
        logger.debug(f"🚀 Отправка bump запроса: game_id={game_id}, categories={category_ids}")
        
        # Убедимся, что у нас есть SID перед bump запросом
        if not self.session.get_sid():
            logger.debug("⚠️ SID отсутствует, получаем через user_info...")
            await self.get_user_info()
        
        response = await self.session.post_json(
            f"{self.config.API_URL}/offers/bump",
            data={"gameId": game_id, "categoryIds": category_ids},
            referer=referer or self.config.BASE_URL,
            include_sid=True,
        )
        
        logger.debug(f"📨 Ответ bump API: {response}")
        
        return {
            "request": {"gameId": game_id, "categoryIds": category_ids},
            "response": response,
        }
        
    # ==================== Пользователи ====================
    
    async def get_user_offers(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Получить все офферы пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            list: Список офферов пользователя
        """
        logger.debug(f"🔍 Запрашиваю лоты пользователя {user_id} через Next.js Data API...")
        page_props = await self._get_user_page_props(user_id)

        categories = page_props.get("userProfileOffers")
        if not categories:
            categories = (page_props.get("bff") or {}).get("userProfileOffers")
        if not categories:
            categories = page_props.get("categoriesWithOffers") or []

        offers = []
        for category in categories:
            category_offers = category.get("offers", [])
            for offer in category_offers:
                offer_id = offer.get("id")
                price = offer.get("price")
                availability = offer.get("availability")
                
                brief = (offer.get("descriptions") or {}).get("rus", {}).get("briefDescription")
                attrs = offer.get("attributes", [])
                labels = [a.get("valueLabel") for a in attrs if a.get("valueLabel")]
                title_parts = [p for p in [brief, *labels] if p]
                title = ", ".join(title_parts) if title_parts else None
                
                offers.append({
                    "id": offer_id,
                    "title": title,
                    "availability": availability,
                    "price": price,
                    "url": f"{self.config.BASE_URL}/offers/{offer_id}" if offer_id else None,
                })
        
        logger.debug(f"✅ Всего собрано лотов: {len(offers)}")
        return offers
    
    async def get_user_categories(self, user_id: int) -> Dict[int, List[int]]:
        """
        Получить все категории с лотами пользователя, сгруппированные по играм
        
        Args:
            user_id: ID пользователя
            
        Returns:
            dict: Словарь {game_id: [category_ids]} - все категории пользователя по играм
        """
        logger.debug(f"🔍 Запрашиваю категории пользователя {user_id}...")
        game_categories = await self._resolve_user_categories(user_id)

        logger.debug(f"📦 Найдено игр: {len(game_categories)}")
        for game_id, cat_ids in game_categories.items():
            logger.debug(f"  🎮 Game {game_id}: категории {cat_ids}")

        return game_categories
    
    # ==================== Поддержка онлайна ====================
    
    async def keep_alive(self) -> bool:
        """
        Поддержка онлайн статуса (heartbeat)
        Отправляет heartbeat запрос к API
        
        Returns:
            True если запрос успешен, False если ошибка
        """
        if not self.session.get_sid():
            try:
                await self.get_user_info()
            except Exception as sid_error:
                logger.debug(f"Не удалось получить SID перед heartbeat: {sid_error}")

        try:
            # Отправляем heartbeat запрос
            await self.session.post_json(
                f"{self.config.API_URL}/user/heartbeat",
                data={},
                referer=f"{self.config.BASE_URL}/",
                include_sid=True,
            )
            return True
        except Exception as heartbeat_error:
            logger.debug(f"Heartbeat endpoint не сработал, пробуем fallback: {heartbeat_error}")

        # Резервные запросы тоже обновляют активность сессии на сайте.
        for fallback_name, fallback_call in (
            ("get_user_info", self.get_user_info),
            ("get_chats", self.get_chats),
        ):
            try:
                await fallback_call()
                logger.debug(f"KeepAlive fallback успешен через {fallback_name}")
                return True
            except Exception as fallback_error:
                logger.debug(f"KeepAlive fallback {fallback_name} не сработал: {fallback_error}")

        return False

    async def is_socket_io_available(self) -> bool:
        """Проверить, доступен ли Socket.IO на Starvell (может быть отключён антиботом)."""
        if self._socket_io_available is not None:
            return self._socket_io_available

        polling_url = f"{self.config.BASE_URL}/socket.io/?EIO=4&transport=polling"
        try:
            status = await asyncio.wait_for(
                self.session.probe_status(polling_url, referer=f"{self.config.BASE_URL}/", timeout_seconds=5),
                timeout=8.0,
            )
            self._socket_io_available = status < 400
        except Exception:
            self._socket_io_available = False

        if not self._socket_io_available:
            logger.info(
                "ℹ️ Socket.IO недоступен на Starvell — онлайн через HTTP heartbeat"
            )
        return self._socket_io_available

    async def connect_online_socket(self):
        """
        Открыть реальный Socket.IO namespace /online, который использует фронт Starvell
        для поддержания онлайн-статуса.
        """
        if not await self.is_socket_io_available():
            raise NotFoundError("Socket.IO отключён на Starvell")

        if not self.session.get_sid():
            try:
                await self.get_user_info()
            except Exception as sid_error:
                logger.debug(f"Не удалось получить SID перед online websocket: {sid_error}")

        return await self.session.ws_connect(
            f"{self.config.BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://')}/socket.io/?EIO=4&transport=websocket",
            referer=f"{self.config.BASE_URL}/",
            headers={
                "origin": self.config.BASE_URL,
                "cache-control": "no-cache",
                "pragma": "no-cache",
            },
            include_sid=True,
        )
