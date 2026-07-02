"""
Сервис вечного онлайна
"""

import asyncio
import logging
from typing import Optional
import aiohttp

from bot.core.config import BotConfig


logger = logging.getLogger("KeepAlive")


class KeepAliveService:
    """
    Сервис для поддержания онлайн статуса на Starvell
    
    HTTP heartbeat — основной метод (Socket.IO может быть отключён антиботом).
    """
    
    def __init__(self, starvell):
        """
        Args:
            starvell: StarvellService instance
        """
        self.starvell = starvell
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._socket_task: Optional[asyncio.Task] = None
        self._interval = BotConfig.KEEP_ALIVE_INTERVAL()
        self._last_success = None
        self._last_socket_success = None
        self._fail_count = 0
        self._socket_fail_count = 0
        self._success_count = 0
        self._socket_success_count = 0
        self._heartbeat_timeout = 25
        self._http_fallback_interval = 30
        self._socket_stale_after = 45
        self._websocket_enabled = True
        self._websocket_disabled_logged = False
        self._socket_namespaces = (
            "/chats",
            "/user-notifications",
            "/user-presence",
            "/viewed-offers",
            "/online",
        )
        self._connected_namespaces = set()
        self._last_socket_packet = None
        self._last_socket_error = None
        
    async def start(self):
        """Запустить сервис"""
        if self._running:
            logger.warning("Сервис вечного онлайна уже запущен")
            return

        if not BotConfig.KEEP_ALIVE_ENABLED():
            logger.info("⏸️ Вечный онлайн отключен в настройках")
            self._running = False
            return

        self._running = True
        try:
            self._task = asyncio.create_task(self._http_heartbeat_loop())
            self._socket_task = asyncio.create_task(self._init_websocket_mode())
            logger.info(f"Сервис вечного онлайна запущен (интервал: {self._interval}s)")
        except Exception as e:
            self._running = False
            logger.error(f"Не удалось запустить KeepAliveTask: {e}")
        
    async def restart_online_socket(self):
        """Restart only the websocket part without restarting the whole bot."""
        if not BotConfig.KEEP_ALIVE_ENABLED():
            return False

        if not self._running:
            await self.start()
            return True

        if not self._websocket_enabled:
            await self._send_heartbeat()
            return self._fail_count == 0

        if self._socket_task:
            self._socket_task.cancel()
            try:
                await self._socket_task
            except asyncio.CancelledError:
                pass

        self._socket_task = asyncio.create_task(self._online_socket_loop())
        return True

    async def force_http_check(self):
        """Run one HTTP heartbeat/fallback check now."""
        await self._send_heartbeat()
        return self._fail_count == 0

    async def stop(self):
        """Остановить сервис"""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._socket_task:
            self._socket_task.cancel()
            try:
                await self._socket_task
            except asyncio.CancelledError:
                pass
            self._socket_task = None

        logger.info("⏹️ Сервис вечного онлайна остановлен")

    async def _init_websocket_mode(self):
        """Проверить Socket.IO в фоне, не блокируя старт бота."""
        try:
            api = getattr(self.starvell, "api", None)
            if not api:
                return
            self._websocket_enabled = await api.is_socket_io_available()
            if self._websocket_enabled:
                await self._online_socket_loop()
            else:
                logger.info("🟢 Вечный онлайн: режим HTTP heartbeat (Socket.IO недоступен)")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"WebSocket init skipped: {e}")

    async def _online_socket_loop(self):
        """Держать открытым Socket.IO namespace /online, как браузер Starvell."""
        while self._running and self._websocket_enabled:
            websocket = None
            try:
                websocket = await asyncio.wait_for(
                    self.starvell.connect_online_socket(),
                    timeout=self._heartbeat_timeout,
                )
                requested_namespaces = set()
                self._connected_namespaces = set()
                namespace_confirmed = False
                logger.info("🟢 Online websocket transport подключён")

                async for message in websocket:
                    if not self._running:
                        break

                    if message.type == aiohttp.WSMsgType.TEXT:
                        payload = message.data
                        self._last_socket_packet = payload[:300]
                        if payload.startswith("0"):
                            for namespace in self._socket_namespaces:
                                await websocket.send_str(f"40{namespace},")
                                requested_namespaces.add(namespace)
                        elif payload == "2":
                            await websocket.send_str("3")
                            if namespace_confirmed:
                                self._mark_socket_success()
                        elif payload.startswith("40/"):
                            namespace = self._extract_namespace(payload)
                            if namespace:
                                self._connected_namespaces.add(namespace)
                            namespace_confirmed = "/online" in self._connected_namespaces
                            self._mark_socket_success()
                            logger.info(f"🟢 Socket.IO namespace подтверждён: {namespace or payload[:80]}")
                        elif payload.startswith("41/"):
                            namespace = self._extract_namespace(payload)
                            if namespace in self._connected_namespaces:
                                self._connected_namespaces.discard(namespace)
                            if namespace in requested_namespaces:
                                self._socket_fail_count += 1
                                self._last_socket_error = f"namespace closed: {payload[:200]}"
                                logger.warning(f"⚠️ Starvell закрыл namespace {namespace}: {payload[:200]}")
                            if namespace == "/online":
                                break
                        elif payload.startswith("41") or payload.startswith("1"):
                            self._last_socket_error = f"socket closed: {payload[:200]}"
                            break
                        elif payload.startswith("44/"):
                            namespace = self._extract_namespace(payload)
                            self._socket_fail_count += 1
                            self._last_socket_error = f"connect error {namespace}: {payload[:200]}"
                            logger.warning(f"⚠️ Socket.IO connect_error {namespace}: {payload[:200]}")
                            if namespace == "/online":
                                break
                        else:
                            if namespace_confirmed:
                                self._mark_socket_success()
                    elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._socket_fail_count += 1
                self._last_socket_error = str(e)
                error_text = str(e).lower()
                if "404" in error_text or "socket.io" in error_text:
                    self._disable_websocket("Socket.IO недоступен на Starvell")
                    break
                if self._socket_fail_count <= 3 or self._socket_fail_count % 10 == 0:
                    logger.warning(
                        f"⚠️ Online websocket /online отвалился: {e} "
                        f"(ошибок подряд: {self._socket_fail_count})"
                    )
            finally:
                if websocket and not websocket.closed:
                    await websocket.close()

            if self._running and self._websocket_enabled:
                await asyncio.sleep(self._socket_reconnect_delay())

    def _disable_websocket(self, reason: str):
        if self._websocket_enabled:
            self._websocket_enabled = False
            if not self._websocket_disabled_logged:
                logger.info(f"ℹ️ {reason} — переключаюсь на HTTP heartbeat")
                self._websocket_disabled_logged = True

    def _mark_socket_success(self):
        self._last_socket_success = asyncio.get_event_loop().time()
        self._socket_fail_count = 0
        self._last_socket_error = None
        self._socket_success_count += 1

    def _extract_namespace(self, payload: str) -> Optional[str]:
        if len(payload) < 3 or not payload.startswith(("40/", "41/", "44/")):
            return None

        namespace_part = payload[2:]
        for separator in (",", "{", "["):
            index = namespace_part.find(separator)
            if index >= 0:
                namespace_part = namespace_part[:index]
                break
        return namespace_part or None

    def _socket_reconnect_delay(self) -> int:
        if self._socket_fail_count <= 0:
            return 10
        return min(120, 10 * min(self._socket_fail_count, 12))
        
    async def _http_heartbeat_loop(self):
        """Основной HTTP heartbeat для поддержания онлайна."""
        logger.debug("KeepAlive HTTP heartbeat loop started")
        while self._running:
            try:
                if self._task and self._task.cancelled():
                    break

                self._interval = max(BotConfig.KEEP_ALIVE_INTERVAL(), self._http_fallback_interval)

                if not BotConfig.KEEP_ALIVE_ENABLED():
                    logger.debug("Вечный онлайн отключен, пропускаем heartbeat")
                    await asyncio.sleep(self._interval)
                    continue

                now = asyncio.get_event_loop().time()
                socket_fresh = (
                    self._websocket_enabled
                    and self._last_socket_success
                    and now - self._last_socket_success < self._socket_stale_after
                )

                if not socket_fresh:
                    await self._send_heartbeat()

                await asyncio.sleep(self._interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле вечного онлайна: {e}", exc_info=True)
                await asyncio.sleep(5)
                
    async def _send_heartbeat(self):
        """Отправить heartbeat запрос"""
        try:
            success = await asyncio.wait_for(
                self.starvell.keep_alive(),
                timeout=self._heartbeat_timeout,
            )
            
            if success:
                self._last_success = asyncio.get_event_loop().time()
                self._fail_count = 0
                self._success_count += 1
                logger.debug("💚 Heartbeat отправлен успешно")
            else:
                self._fail_count += 1
                if self._fail_count <= 3 or self._fail_count % 10 == 0:
                    logger.warning(f"⚠️ Heartbeat не удался (ошибок подряд: {self._fail_count})")
                
        except asyncio.TimeoutError:
            self._fail_count += 1
            logger.warning(f"⚠️ Heartbeat завис дольше {self._heartbeat_timeout}s (ошибок подряд: {self._fail_count})")
        except Exception as e:
            self._fail_count += 1
            logger.error(f"❌ Ошибка отправки heartbeat: {e}")
            
    def get_status(self) -> dict:
        """
        Получить статус сервиса
        
        Returns:
            dict с информацией о статусе
        """
        return {
            "running": self._running,
            "enabled": BotConfig.KEEP_ALIVE_ENABLED(),
            "interval": self._interval,
            "websocket_enabled": self._websocket_enabled,
            "last_success": self._last_success,
            "last_socket_success": self._last_socket_success,
            "fail_count": self._fail_count,
            "success_count": self._success_count,
            "socket_fail_count": self._socket_fail_count,
            "socket_success_count": self._socket_success_count,
            "connected_namespaces": sorted(self._connected_namespaces),
            "last_socket_packet": self._last_socket_packet,
            "last_socket_error": self._last_socket_error,
        }
