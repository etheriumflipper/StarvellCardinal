"""
Модуль авто-поднятия лотов 
"""

import asyncio
import logging
import time
from typing import Dict, Optional, List
from datetime import datetime


from bot.core.config import BotConfig


logger = logging.getLogger("RAIS")


class AutoRaiseService:
    """Сервис автоматического поднятия лотов)"""
    
    def __init__(self, starvell_service, notification_manager=None):
        self.starvell = starvell_service
        self.notifier = notification_manager
        self.raise_time: Dict[int, int] = {}  # game_id -> timestamp следующего поднятия
        self.raised_time: Dict[int, int] = {}  # game_id -> timestamp последнего поднятия
        self._task: asyncio.Task = None
        self._force_check = asyncio.Event()  # Событие для принудительной проверки
        self._last_categories: Dict[int, List[int]] = {}  # game_id -> список категорий (для отслеживания изменений)
        self._initial_check_done = False  # Флаг первой проверки
        self._lock = asyncio.Lock()  # Защита словарей от race conditions
        
    async def start(self):
        """Запустить сервис"""
        self._task = asyncio.create_task(self._raise_loop())
        if BotConfig.AUTO_BUMP_ENABLED():
            logger.info("🔵 Цикл авто-поднятия запущен")
        else:
            logger.info("⏸️ Цикл авто-поднятия в режиме ожидания (отключено в настройках)")
    
    async def trigger_immediate_check(self):
        """Триггер немедленной проверки и поднятия (при включении)"""
        self._force_check.set()
    
    async def stop(self):
        """Остановить сервис"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Сервис авто-поднятия остановлен")
    
    async def _raise_loop(self):
        """Бесконечный цикл поднятия лотов"""
        while True:
            try:
                # Проверяем, включено ли автоподнятие
                if not BotConfig.AUTO_BUMP_ENABLED():
                    # Ждём события принудительной проверки или 10 секунд
                    try:
                        await asyncio.wait_for(self._force_check.wait(), timeout=10)
                        self._force_check.clear()
                        # Проверяем ещё раз - может включили
                        if not BotConfig.AUTO_BUMP_ENABLED():
                            continue
                        logger.info("✅ Авто-поднятие включено! Запускаю цикл...")
                    except asyncio.TimeoutError:
                        pass
                    continue
                
                # Попытка поднять лоты напрямую (проверка наличия через API bump)
                logger.debug("🚀 Запускаю процедуру поднятия лотов...")
                next_time = await self._raise_lots()
                
                # Рассчитываем задержку
                delay = next_time - int(time.time())
                
                if delay <= 0:
                    continue
                
                # Спим с периодическим логированием оставшегося времени
                await self._sleep_with_countdown(delay)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле поднятия: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    async def _sleep_with_countdown(self, total_seconds: int, chunk_seconds: int = 600):
        """
        Асинхронный sleep с периодическим логированием обратного отсчета
        и обязательным пробуждением не реже чем раз в chunk_seconds (по умолчанию 10 минут)
        для повторной проверки наличия новых лотов.
        
        Args:
            total_seconds: Общее время ожидания в секундах
            chunk_seconds: Максимальная непрерывная пауза перед промежуточной проверкой
        """
        log_intervals = [
            3600, 3000, 2400, 1800, 1200, 900, 600, 300, 180, 120, 60, 30, 10, 5, 3, 2, 1
        ]
        remaining = total_seconds
        logger.debug(f"⏳ Ожидание до следующего поднятия: {self._time_to_str(total_seconds)} (chunk {chunk_seconds}s)")

        while remaining > 0:
            step = min(remaining, chunk_seconds)
            end_time = int(time.time()) + step

            while True:
                current_time = int(time.time())
                left_in_step = end_time - current_time

                if left_in_step <= 0:
                    break

                if self._force_check.is_set():
                    self._force_check.clear()
                    logger.info("🔄 Принудительная проверка - прерываем ожидание")
                    return

                # Логируем только ключевые точки и не засоряем INFO
                for interval in log_intervals:
                    if left_in_step == interval:
                        logger.debug(f"⏲️ До следующего поднятия осталось: {self._time_to_str(remaining)}")
                        break

                # Оптимизированный sleep - спим до 10 секунд вместо 1 секунды
                sleep_time = min(left_in_step, 10)
                await asyncio.sleep(sleep_time)

            remaining = max(0, remaining - step)

            # Если ещё осталось ждать, выходим в основной цикл для повторной проверки новых лотов
            if remaining > 0:
                logger.debug("🔁 Промежуточная проверка новых лотов после 10 минут ожидания")
                return
    
    async def _raise_lots(self) -> int:
        """
        Автоматическое поднятие ВСЕХ лотов пользователя
        Определяет категории динамически из профиля
        Оптимизирует таймеры - группирует лоты с близким временем поднятия
        
        Returns:
            Timestamp следующего вызова
        """
        current_time = int(time.time())
        interval = BotConfig.AUTO_BUMP_INTERVAL()
        
        # Для сбора времени следующих поднятий всех игр
        all_next_times = []
        
        # Определяем, нужно ли логировать подробно
        # Логируем только при: 1) первой проверке, 2) обнаружении новых категорий
        is_first_check = not self._initial_check_done
        verbose_logging = is_first_check
        
        if verbose_logging:
            logger.info("🔍 Начинаю автоматическое определение категорий...")
        
        try:
            # Получаем ID пользователя
            user_info = await self.starvell.get_user_info()
            user_id = user_info.get("user", {}).get("id")
            
            if not user_id:
                logger.error("❌ Не удалось получить ID пользователя")
                return current_time + 300  # Попробуем через 5 минут
            
            # Получаем все категории пользователя автоматически
            game_categories = await self.starvell.api.get_user_categories(user_id)
            
            if not game_categories:
                logger.warning("📭 Не найдено категорий с лотами")
                logger.warning(f"👉 Starvell может блокировать профиль. Проверьте: https://starvell.com/users/{user_id}")
                logger.warning("💡 Категории подтянутся из заказов/кэша, если лоты уже продавались")
                return current_time + 600  # Попробуем через 10 минут
            
            # Проверяем, изменились ли категории
            categories_changed = False
            async with self._lock:
                for game_id, categories in game_categories.items():
                    if game_id not in self._last_categories or self._last_categories[game_id] != categories:
                        categories_changed = True
                        self._last_categories[game_id] = categories
            
            # Если категории изменились, логируем подробно
            if categories_changed and not verbose_logging:
                verbose_logging = True
                logger.info("🆕 Обнаружены новые категории!")
            
            if verbose_logging:
                logger.info(f"✅ Найдено игр с лотами: {len(game_categories)}")
            
            # Поднимаем лоты для каждой игры
            for game_id, categories in game_categories.items():
                logger.debug(f"🎮 Обрабатываю игру {game_id}, категории: {categories}")

                # Проверяем, не рано ли поднимать эту игру
                async with self._lock:
                    saved_time = self.raise_time.get(game_id)

                if saved_time and saved_time > current_time:
                    remaining = saved_time - current_time
                    if verbose_logging:
                        logger.info(f"⏰ Игра {game_id}: поднятие через {self._time_to_str(remaining)}")
                    all_next_times.append(saved_time)
                    continue

                # Поднимаем лоты этой игры
                bump_next_time = await self._raise_game_lots(game_id, categories, interval, current_time, verbose_logging)

                # Добавляем в список времен
                if bump_next_time:
                    all_next_times.append(bump_next_time)
            
            # Помечаем, что первая проверка завершена
            if is_first_check:
                self._initial_check_done = True
                
        except Exception as e:
            logger.error(f"❌ Ошибка в процессе поднятия: {e}", exc_info=True)
            return current_time + 600  # Попробуем через 10 минут
            
        # Оптимизация: группируем близкие по времени поднятия
        if all_next_times:
            next_call = self._optimize_next_call(all_next_times, current_time)
            if verbose_logging:
                logger.info(f"📅 Следующая проверка через {self._time_to_str(next_call - current_time)}")
            return next_call
        else:
            # Если нет запланированных поднятий, используем стандартный интервал
            return current_time + interval
    
    def _optimize_next_call(self, next_times: List[int], current_time: int) -> int:
        """
        Оптимизирует время следующей проверки
        Группирует лоты с близким временем поднятия (в пределах получаса)
        
        Args:
            next_times: Список времен следующих поднятий
            current_time: Текущее время
            
        Returns:
            Оптимизированное время следующей проверки
        """
        if not next_times:
            return current_time + BotConfig.AUTO_BUMP_INTERVAL()
        
        # Сортируем времена
        sorted_times = sorted(next_times)
        earliest = sorted_times[0]
        
        # Время до ближайшего поднятия
        time_to_earliest = earliest - current_time
        
        # Округляем вверх до ближайшего получаса (1800 секунд = 30 минут)
        # Пример: если осталось 1:20 (4800с), 1:11 (4260с), 1:01 (3660с) - все округлятся до 1:30 (5400с)
        half_hour = 1800
        
        # Если времени меньше получаса - не округляем, возвращаем как есть
        if time_to_earliest < half_hour:
            logger.debug(f"⚡ Времени мало ({self._time_to_str(time_to_earliest)}), не округляем")
            return earliest
        
        # Округляем вверх до ближайшего получаса
        rounded = ((time_to_earliest + half_hour - 1) // half_hour) * half_hour
        optimized_time = current_time + rounded
        
        # Проверяем, сколько лотов попадает в этот интервал (±15 минут)
        tolerance = 900  # 15 минут
        grouped_count = sum(1 for t in sorted_times if abs(t - optimized_time) <= tolerance)
        
        if grouped_count > 1:
            logger.debug(f"🔄 Оптимизация: {grouped_count} игр(ы) будут проверены вместе")
            
            # Выводим детали группировки
            grouped_games = []
            for idx, t in enumerate(sorted_times):
                if abs(t - optimized_time) <= tolerance:
                    time_diff = t - current_time
                    grouped_games.append(self._time_to_str(time_diff))
                    logger.debug(f"   - Игра #{idx+1}: запланирована через {self._time_to_str(time_diff)}")
            
                if len(grouped_games) > 1:
                    logger.debug(f"   Времена: {', '.join(grouped_games[:3])}" + 
                               (f" + ещё {len(grouped_games)-3}" if len(grouped_games) > 3 else ""))
        else:
            logger.debug(f"⏰ Одна игра, время: {self._time_to_str(time_to_earliest)}")
        
        return optimized_time
    
    async def _raise_game_lots(self, game_id: int, categories: List[int], interval: int, current_time: int, verbose_logging: bool = False) -> int:
        """
        Поднять лоты конкретной игры
        
        Args:
            game_id: ID игры
            categories: Список ID категорий
            interval: Интервал между поднятиями
            current_time: Текущее время
            verbose_logging: Флаг подробного логирования
            
        Returns:
            Timestamp следующего поднятия
        """
        raise_ok = False
        time_delta = ""
        
        try:
            await asyncio.sleep(1)
            
            # Вызываем API поднятия
            result = await self.starvell.bump_offers(game_id, categories)
            
            # Проверяем успешность
            response = result.get("response", {})
            
            if response.get("success") or (not response.get("error") and response.get("success") != False):
                logger.info(f"✅ Лоты игры ID={game_id} (категории {categories}) подняты!")
                raise_ok = True

                # Обновляем временные метки
                new_time = int(time.time())
                async with self._lock:
                    last_time = self.raised_time.get(game_id)
                    self.raised_time[game_id] = new_time

                # Форматируем время с последнего поднятия
                if last_time:
                    delta = new_time - last_time
                    time_delta = f" Последнее поднятие: {self._time_to_str(delta)} назад."

                # Рассчитываем следующее поднятие
                next_time = new_time + interval
                async with self._lock:
                    self.raise_time[game_id] = next_time
                
                # Округляем оставшееся время до получаса для вывода
                rounded_interval = ((interval + 1799) // 1800) * 1800
                logger.info(f"⏰ Следующее поднятие через ~{self._time_to_str(rounded_interval)}.{time_delta}")
                
                # Отправляем уведомление
                if self.notifier:
                    try:
                        await self.notifier.notify_lots_raised(game_id, time_delta)
                    except Exception as e:
                        logger.debug(f"Ошибка отправки уведомления: {e}")
                        
                return next_time
            else:
                # API вернул ошибку
                error = response.get("error") or response.get("message") or "Неизвестная ошибка"
                raise Exception(error)
                
        except Exception as e:
            error_msg = str(e)
            
            # Проверяем, есть ли указание на отсутствие лотов
            if any(keyword in error_msg.lower() for keyword in ["нет лотов", "no offers", "no lots", "немає лотів"]):
                logger.warning(f"📭 API сообщает: нет лотов для поднятия (game_id={game_id}, categories={categories})")
                logger.warning(f"💡 Категории были определены автоматически")
                logger.warning(f"💡 Возможно, все лоты этой игры сняты с продажи")
                return current_time + 300  # Повторим через 5 минут
                
            # Проверяем, содержит ли ошибка информацию о времени ожидания
            elif any(keyword in error_msg.lower() for keyword in ["подождите", "wait", "зачекайте", "через"]):
                # Парсим время ожидания из ошибки API
                wait_time = self._parse_wait_time(error_msg)
                
                if wait_time:
                    # Округляем время до получаса вверх для вывода
                    rounded_wait = ((wait_time + 1799) // 1800) * 1800
                    
                    if verbose_logging:
                        logger.debug(
                            f"⏳ Лоты игры ID={game_id} уже поднимались недавно."
                        )
                        logger.debug(f"📨 API сообщает: \"{error_msg}\"")
                        logger.debug(f"⏰ Следующее поднятие через ~{self._time_to_str(rounded_wait)}")
                    
                    # Устанавливаем время следующего поднятия
                    next_time = current_time + wait_time
                    async with self._lock:
                        self.raise_time[game_id] = next_time
                    return next_time
                else:
                    logger.error(f"❌ Непредвиденная ошибка при поднятии лотов игры ID={game_id}. Пауза на 10 секунд...")
                    logger.debug("TRACEBACK", exc_info=True)
                    await asyncio.sleep(10)
                    return current_time + 60
                    
            elif "429" in error_msg or "403" in error_msg or "503" in error_msg:
                # Ошибка сервера - ждём 1 минуту
                logger.warning(f"⚠️ Ошибка сервера при поднятии лотов игры ID={game_id}. Пауза на 1 минуту...")
                await asyncio.sleep(60)
                return current_time + 60
                
            else:
                # Другая ошибка
                await asyncio.sleep(10)
                return current_time + 60
    
    def _parse_wait_time(self, message: str) -> int:
        """
        Извлечь время ожидания из сообщения об ошибке
        
        Args:
            message: Сообщение об ошибке от API
            
        Returns:
            Время ожидания в секундах, или 0 если не удалось распарсить
        """
        import re
        
        message_lower = message.lower()
        total_seconds = 0
        
        # Ищем часы (hours) - учитываем множественное число
        hours_patterns = [
            r'(\d+(?:\.\d+)?)\s*час[аов]?',  # "3 часа", "1 час", "2 часов"
            r'(\d+(?:\.\d+)?)\s*hour[s]?',   # "2 hours", "1 hour"
            r'(\d+(?:\.\d+)?)\s*hr[s]?',     # "2 hrs", "1 hr"
            r'(\d+(?:\.\d+)?)\s*h\b',        # "2h"
        ]
        
        for pattern in hours_patterns:
            match = re.search(pattern, message_lower)
            if match:
                hours = float(match.group(1))
                total_seconds += int(hours * 3600)
                break  # Нашли часы, переходим к минутам
        
        # Ищем минуты (minutes) - учитываем множественное число
        minutes_patterns = [
            r'(\d+)\s*минут[ыа]?',  # "30 минут", "1 минута", "2 минуты"
            r'(\d+)\s*minute[s]?',  # "30 minutes", "1 minute"
            r'(\d+)\s*min[s]?',     # "30 mins"
            r'(\d+)\s*м\b',         # "30 м"
        ]
        
        for pattern in minutes_patterns:
            match = re.search(pattern, message_lower)
            if match:
                minutes = int(match.group(1))
                total_seconds += minutes * 60
                break  # Нашли минуты, переходим к секундам
        
        # Ищем секунды (seconds) - учитываем множественное число
        seconds_patterns = [
            r'(\d+)\s*секунд[ыа]?',  # "45 секунд", "1 секунда", "2 секунды"
            r'(\d+)\s*second[s]?',   # "45 seconds", "1 second"
            r'(\d+)\s*sec[s]?',      # "45 secs"
            r'(\d+)\s*с\b',          # "45 с"
        ]
        
        for pattern in seconds_patterns:
            match = re.search(pattern, message_lower)
            if match:
                seconds = int(match.group(1))
                total_seconds += seconds
                break
        
        # Если нашли хоть что-то, возвращаем
        if total_seconds > 0:
            return total_seconds
        
        # Если не нашли конкретное время, но есть слова ожидания, возвращаем дефолтное значение
        if any(keyword in message_lower for keyword in ["подождите", "wait", "зачекайте"]):
            return 3600  # 1 час по умолчанию
        
        return 0  # Не удалось распарсить
    
    @staticmethod
    def _time_to_str(seconds: int) -> str:
        """
        Преобразовать секунды в читабельный формат
        
        Args:
            seconds: Количество секунд
            
        Returns:
            Форматированная строка вида "2ч 30мин" или "45сек"
        """
        if seconds >= 3600:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"{hours}ч {minutes}мин"
            return f"{hours}ч"
        elif seconds >= 60:
            minutes = seconds // 60
            secs = seconds % 60
            if secs > 0:
                return f"{minutes}мин {secs}сек"
            return f"{minutes}мин"
        else:
            return f"{seconds}сек"
