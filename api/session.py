"""Управление HTTP сессиями"""

import asyncio
import time
import json
from typing import Optional, Dict, Any
import aiohttp
from aiohttp import ClientTimeout, ClientResponseError

from .config import Config
from .exceptions import (
    StarAPIError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    ForbiddenError,
    ServerError,
)
from .rate_limiter import throttle


class SessionManager:
    """Менеджер HTTP сессий с retry логикой"""

    def __init__(self, session_cookie: str, config: Config):
        # Валидация session_cookie
        if not session_cookie or not isinstance(session_cookie, str):
            raise ValueError("session_cookie должен быть непустой строкой")
        if len(session_cookie) < 10:
            raise ValueError("session_cookie слишком короткий (минимум 10 символов)")

        self.session_cookie = session_cookie
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._sid_cookie: Optional[str] = None
        
    async def __aenter__(self):
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def start(self):
        """Создать сессию"""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
            
    async def close(self):
        """Закрыть сессию"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            
    def _get_headers(self, referer: str = None, extra: Dict[str, str] = None) -> Dict[str, str]:
        """Получить заголовки для запроса"""
        headers = {
            "accept": "*/*",
            "accept-language": "ru,en;q=0.9",
            "user-agent": self.config.user_agent,
            **Config.BROWSER_HEADERS,
        }
        
        if referer:
            headers["referer"] = referer
            headers["origin"] = self.config.BASE_URL
            
        if extra:
            headers.update(extra)
            
        return headers
        
    def _get_cookies(self, include_sid: bool = False) -> Dict[str, str]:
        """Получить cookies для запроса"""
        cookies = {
            "session": self.session_cookie,
            **Config.DEFAULT_COOKIES,
        }
        
        if include_sid and self._sid_cookie:
            cookies["sid"] = self._sid_cookie
            
        return cookies
        
    def set_sid(self, sid: Optional[str]):
        """Установить SID cookie"""
        self._sid_cookie = sid
        
    def get_sid(self) -> Optional[str]:
        """Получить SID cookie"""
        return self._sid_cookie
        
    async def get_json(
        self,
        url: str,
        referer: str = None,
        headers: Dict[str, str] = None,
        include_sid: bool = False,
    ) -> Any:
        """GET запрос с получением JSON"""
        if self._session is None:
            await self.start()
            
        retry_count = self.config.max_retries
        request_headers = self._get_headers(referer, headers)
        cookies = self._get_cookies(include_sid)
        
        last_error = None
        
        for attempt in range(retry_count):
            try:
                await throttle()
                async with self._session.request(
                    "GET",
                    url,
                    headers=request_headers,
                    cookies=cookies,
                ) as resp:
                    # Обработка статус кодов
                    if resp.status == 401:
                        raise AuthenticationError("Неверный session cookie")
                    elif resp.status == 403:
                        raise ForbiddenError(f"Доступ запрещён: {url}")
                    elif resp.status == 404:
                        raise NotFoundError(f"Ресурс не найден: {url}")
                    elif resp.status == 429:
                        raise RateLimitError("Превышен лимит запросов")
                    elif resp.status >= 500:
                        raise ServerError(f"Ошибка сервера: {resp.status}")
                    
                    resp.raise_for_status()
                    return await resp.json()
                    
            except (ClientResponseError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e

                # Не повторяем запросы для определенных ошибок
                if isinstance(e, (AuthenticationError, NotFoundError, RateLimitError, ForbiddenError)):
                    raise

                # Последняя попытка
                if attempt == retry_count - 1:
                    break

                # Ждем перед следующей попыткой
                await asyncio.sleep(self.config.RETRY_DELAY * (attempt + 1))
                
        # Если все попытки провалились
        if last_error:
            raise StarAPIError(f"Не удалось выполнить запрос после {retry_count} попыток: {last_error}")
        raise StarAPIError("Неизвестная ошибка при выполнении запроса")
            
    async def post_json(
        self,
        url: str,
        data: Any,
        referer: str = None,
        headers: Dict[str, str] = None,
        include_sid: bool = False,
    ) -> Any:
        """POST запрос с отправкой и получением JSON"""
        if self._session is None:
            await self.start()
            
        retry_count = self.config.max_retries
        headers = headers or {}
        headers["content-type"] = "application/json"
        request_headers = self._get_headers(referer, headers)
        cookies = self._get_cookies(include_sid)
        
        last_error = None
        
        for attempt in range(retry_count):
            try:
                await throttle()
                async with self._session.request(
                    "POST",
                    url,
                    headers=request_headers,
                    cookies=cookies,
                    json=data,
                ) as resp:
                    # Для ошибок читаем тело ответа для отладки
                    if resp.status >= 400:
                        try:
                            error_body = await resp.text()
                            # Пытаемся распарсить как JSON
                            try:
                                error_data = json.loads(error_body)
                                error_message = error_data.get("message") or error_data.get("error") or error_body
                            except:
                                error_message = error_body
                        except:
                            error_message = f"HTTP {resp.status}"
                    
                    # Обработка статус кодов
                    if resp.status == 400:
                        raise StarAPIError(f"Bad Request (400): {error_message}")
                    elif resp.status == 401:
                        raise AuthenticationError("Неверный session cookie")
                    elif resp.status == 403:
                        raise ForbiddenError(f"Доступ запрещён: {url}")
                    elif resp.status == 404:
                        raise NotFoundError(f"Ресурс не найден: {url}")
                    elif resp.status == 429:
                        raise RateLimitError("Превышен лимит запросов")
                    elif resp.status >= 500:
                        raise ServerError(f"Ошибка сервера: {resp.status}")
                    
                    resp.raise_for_status()
                    
                    content_type = resp.headers.get("Content-Type", "")
                    
                    if "application/json" in content_type.lower():
                        return await resp.json()
                    else:
                        text = await resp.text()
                        return {"status": resp.status, "text": text}
                    
            except (ClientResponseError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e

                # Не повторяем запросы для определенных ошибок
                if isinstance(e, (AuthenticationError, NotFoundError, RateLimitError, ForbiddenError)):
                    raise

                # Последняя попытка
                if attempt == retry_count - 1:
                    break

                # Ждем перед следующей попыткой
                await asyncio.sleep(self.config.RETRY_DELAY * (attempt + 1))
                
        # Если все попытки провалились
        if last_error:
            raise StarAPIError(f"Не удалось выполнить запрос после {retry_count} попыток: {last_error}")
        raise StarAPIError("Неизвестная ошибка при выполнении запроса")

    async def probe_status(
        self,
        url: str,
        referer: str = None,
        timeout_seconds: float = 5,
    ) -> int:
        """Быстрая проверка URL без retry — для диагностики при старте."""
        if self._session is None:
            await self.start()

        request_headers = self._get_headers(referer)
        cookies = self._get_cookies(False)
        timeout = ClientTimeout(total=timeout_seconds, connect=timeout_seconds)
        await throttle()
        async with self._session.request(
            "GET",
            url,
            headers=request_headers,
            cookies=cookies,
            timeout=timeout,
        ) as resp:
            return resp.status

    async def head_headers(
        self,
        url: str,
        referer: str = None,
        timeout_seconds: float = 5,
    ) -> Dict[str, str]:
        """HEAD-запрос и заголовки ответа (для QRATOR-диагностики)."""
        if self._session is None:
            await self.start()

        request_headers = self._get_headers(referer)
        cookies = self._get_cookies(False)
        timeout = ClientTimeout(total=timeout_seconds, connect=timeout_seconds)
        await throttle()
        async with self._session.request(
            "HEAD",
            url,
            headers=request_headers,
            cookies=cookies,
            timeout=timeout,
        ) as resp:
            return {k: v for k, v in resp.headers.items()}

    async def ws_connect(
        self,
        url: str,
        referer: str = None,
        headers: Dict[str, str] = None,
        include_sid: bool = False,
    ) -> aiohttp.ClientWebSocketResponse:
        """Открыть WebSocket с теми же cookies/headers, что и обычные запросы."""
        if self._session is None:
            await self.start()

        request_headers = self._get_headers(referer, headers)
        cookies = self._get_cookies(include_sid)
        request_headers.setdefault(
            "cookie",
            "; ".join(f"{key}={value}" for key, value in cookies.items() if value is not None),
        )
        return await self._session.ws_connect(
            url,
            headers=request_headers,
            autoping=False,
            heartbeat=None,
        )
                
    async def get_text(
        self,
        url: str,
        referer: str = None,
        headers: Dict[str, str] = None,
        include_sid: bool = False,
    ) -> str:
        """GET запрос с получением текста"""
        if self._session is None:
            await self.start()
            
        retry_count = self.config.max_retries
        request_headers = self._get_headers(referer, headers)
        cookies = self._get_cookies(include_sid)
        
        last_error = None
        
        for attempt in range(retry_count):
            try:
                await throttle()
                async with self._session.request(
                    "GET",
                    url,
                    headers=request_headers,
                    cookies=cookies,
                ) as resp:
                    # Обработка статус кодов
                    if resp.status == 401:
                        raise AuthenticationError("Неверный session cookie")
                    elif resp.status == 403:
                        raise ForbiddenError(f"Доступ запрещён: {url}")
                    elif resp.status == 404:
                        raise NotFoundError(f"Ресурс не найден: {url}")
                    elif resp.status == 429:
                        raise RateLimitError("Превышен лимит запросов")
                    elif resp.status >= 500:
                        raise ServerError(f"Ошибка сервера: {resp.status}")
                    
                    resp.raise_for_status()
                    return await resp.text()
                    
            except (ClientResponseError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e

                # Не повторяем запросы для определенных ошибок
                if isinstance(e, (AuthenticationError, NotFoundError, RateLimitError, ForbiddenError)):
                    raise

                # Последняя попытка
                if attempt == retry_count - 1:
                    break

                # Ждем перед следующей попыткой
                await asyncio.sleep(self.config.RETRY_DELAY * (attempt + 1))
                
        # Если все попытки провалились
        if last_error:
            raise StarAPIError(f"Не удалось выполнить запрос после {retry_count} попыток: {last_error}")
        raise StarAPIError("Неизвестная ошибка при выполнении запроса")
