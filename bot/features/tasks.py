"""
Фоновые задачи бота
"""

import asyncio
import logging
from datetime import datetime
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.core.config import BotConfig, get_config_manager
from bot.core.services import StarvellService
from bot.core.storage import Database
from bot.features.autoticket import get_autoticket_service


logger = logging.getLogger(__name__)

logging.getLogger('apscheduler').setLevel(logging.ERROR)


class BackgroundTasks:
    """Управление фоновыми задачами"""
    
    def __init__(self, bot: Bot, starvell: StarvellService, db: Database, notifier=None, auto_response=None):
        self.bot = bot
        self.starvell = starvell
        self.db = db
        self.notifier = notifier
        self.auto_response = auto_response
        self.scheduler = AsyncIOScheduler()
        self._seen_messages: dict[str, set[str]] = {}  # chat_id -> set of message_ids
        self._first_check_messages = True  # Флаг первой проверки после запуска
        self._first_check_orders = True  # Флаг первой проверки заказов после запуска
        self._auto_ticket_first_run_done = False  # Флаг первого запуска авто-тикетов
        
    def start(self):
        """Запустить фоновые задачи"""
        # Проверка новых сообщений
        chat_interval = 5
        self.scheduler.add_job(
            self._check_new_messages_loop,
            'interval',
            seconds=max(1, int(chat_interval)),
            id='check_messages',
        )
        
        # Проверка новых заказов
        orders_interval = get_config_manager().get('Monitor', 'ordersPollInterval', 5)
        self.scheduler.add_job(
            self._check_new_orders_loop,
            'interval',
            seconds=max(1, int(orders_interval)),
            id='check_orders',
        )
        
        # Авто-bump офферов
        if BotConfig.AUTO_BUMP_ENABLED():
            self.scheduler.add_job(
                self._auto_bump,
                'interval',
                seconds=BotConfig.AUTO_BUMP_INTERVAL(),
                id='auto_bump',
            )

        # Авто-тикеты
        if BotConfig.AUTO_TICKET_ENABLED():
            # Запускаем первую проверку через 10 секунд после старта
            # (даём время на инициализацию и авторизацию)
            import datetime as dt
            first_run_time = dt.datetime.now() + dt.timedelta(seconds=10)
            self.scheduler.add_job(
                self._check_auto_ticket_with_init,
                'date',
                run_date=first_run_time,
                id='auto_ticket_init',
            )
            # Затем запускаем по таймеру
            self.scheduler.add_job(
                self._check_auto_ticket_loop,
                'interval',
                seconds=BotConfig.AUTO_TICKET_INTERVAL(),
                id='auto_ticket',
            )
        
        # Проверка автоответов (каждые 30 секунд)
        if self.auto_response:
            self.scheduler.add_job(
                self._check_auto_responses,
                'interval',
                seconds=30,
                id='auto_responses',
            )
            
        # Очистка старых данных (раз в день)
        self.scheduler.add_job(
            self._cleanup_old_data,
            'cron',
            hour=3,
            minute=0,
            id='cleanup',
        )
        
        self.scheduler.start()
        logger.info("Фоновые задачи запущены")
        
    def stop(self):
        """Остановить фоновые задачи"""
        self.scheduler.shutdown()
        logger.info("Фоновые задачи остановлены")
        
    async def _check_new_messages_loop(self):
        """Polling цикл для проверки новых сообщений"""
        try:
            # ВСЕГДА проверяем сообщения (для плагинов и кастомных команд)
            # Уведомления будут отправлены только если включены (проверка внутри notify_new_message)
            await self._check_new_messages()
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке сообщений: {e}", exc_info=True)
            
    async def _check_new_orders_loop(self):
        """Polling цикл для проверки новых заказов """
        try:
            # ВСЕГДА проверяем заказы (для плагинов)
            # Уведомления будут отправлены только если включены (проверка внутри notify_new_order)
            await self._check_new_orders()
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке заказов: {e}", exc_info=True)
            
    async def _check_new_messages(self):
        """Проверка новых сообщений"""
        try:
            new_messages = await self.starvell.check_new_messages()
            
            if not self.notifier:
                logger.warning("Менеджер уведомлений не инициализирован")
                return
            
            # Логируем количество найденных новых сообщений
            if new_messages:
                if BotConfig.DEBUG():
                    logger.debug(f"📬 Получено {len(new_messages)} новых сообщений от API")
            
            for msg_data in new_messages:
                chat_id = str(msg_data.get("chat_id", ""))
                message = msg_data.get("message", {})
                chat = msg_data.get("chat", {})
                
                author_id = message.get("authorId", "N/A")
                content = message.get("content") or message.get("text", "")
                message_id = message.get("id")
                
                # Пропускаем сообщения без контента
                if not content:
                    continue
                
                # Проверяем черный список по ID
                config = get_config_manager()
                blacklist_section = f"Blacklist.{author_id}"
                if config._config.has_section(blacklist_section):
                    if BotConfig.DEBUG():
                        logger.debug(f"Сообщение от пользователя {author_id} игнорируется (в черном списке)")
                    continue
                
                # Получаем username и роли напрямую из данных сообщения
                # API возвращает message.author.username и message.author.roles
                author_username = None
                author_roles = []
                author_data = message.get("author", {})
                if author_data:
                    author_username = author_data.get("username") or author_data.get("name")
                    author_roles = author_data.get("roles", [])
                
                # Если нет в сообщении, пробуем найти в participants чата
                if not author_username and chat:
                    participants = chat.get("participants", [])
                    for participant in participants:
                        if str(participant.get("id")) == str(author_id):
                            author_username = participant.get("username") or participant.get("name")
                            break
                
                # Пропускаем свои сообщения (проверяем по ID из кэша или из author)
                try:
                    # Используем кэшированный user_id если он есть
                    if not hasattr(self, '_my_user_id'):
                        user_info = await self.starvell.get_user_info()
                        self._my_user_id = str(user_info.get("user", {}).get("id", ""))
                    
                    if str(author_id) == self._my_user_id:
                        continue
                except Exception:
                    pass
                
                # Проверяем, не уведомляли ли уже об этом сообщении
                if chat_id not in self._seen_messages:
                    self._seen_messages[chat_id] = set()
                    
                if message_id and message_id in self._seen_messages[chat_id]:
                    continue
                
                # Проверяем, является ли сообщение от поддержки/модерации
                is_support = author_roles and ("SUPPORT" in author_roles or "MODERATOR" in author_roles or "ADMIN" in author_roles)
                
                # Отправляем уведомление через NotificationManager
                if is_support:
                    # Уведомление о сообщении от поддержки (если включено)
                    await self.notifier.notify_support_message(
                        chat_id=chat_id,
                        author=str(author_id),
                        content=content,
                        message_id=str(message_id) if message_id else None,
                        author_nickname=author_username,
                        author_roles=author_roles
                    )
                else:
                    # Обычное уведомление о новом сообщении
                    await self.notifier.notify_new_message(
                        chat_id=chat_id,
                        author=str(author_id),
                        content=content,
                        message_id=str(message_id) if message_id else None,
                        author_nickname=author_username  
                    )
                
                # Запоминаем это сообщение
                if message_id:
                    self._seen_messages[chat_id].add(message_id)
                    
                # Проверяем кастомные команды
                await self._check_custom_command(chat_id, content, author_id)
                
                # Логируем с указанием роли если есть
                role_prefix = f"[{', '.join(author_roles)}] " if author_roles else ""
                display_name = author_username or author_id
                logger.info(f"📩 Новое сообщение от {role_prefix}{display_name}: {content[:50]}...")
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке новых сообщений: {e}", exc_info=True)
            
    async def _check_new_orders(self):
        """Проверка новых заказов"""
        try:
            new_orders = await self.starvell.check_new_orders()

            if self._first_check_orders:
                primed_orders = 0
                for order in new_orders:
                    order_id = order.get("id")
                    status = order.get("status")
                    if not order_id:
                        continue
                    await self.starvell.db.set_last_order(order_id, status or "CREATED")
                    primed_orders += 1

                self._first_check_orders = False

                if primed_orders:
                    logger.info(
                        f"🧊 Первый запуск: кэш заказов прогрет без уведомлений ({primed_orders} заказов)"
                    )
                else:
                    logger.info("🧊 Первый запуск: активных заказов для прогрева кэша не найдено")
                return
            
            if not self.notifier:
                logger.warning("Менеджер уведомлений не инициализирован")
                return
            
            # Логируем количество найденных новых заказов
            if new_orders:
                logger.debug(f"📦 Получено {len(new_orders)} новых заказов от API")
            
            for order in new_orders:
                order_id = str(order.get("id", ""))
                if not order_id:
                    continue
                
                status = order.get("status", "CREATED")
                
                # Отправляем уведомление ТОЛЬКО при статусе CREATED
                if status != "CREATED":
                    continue
                
                # Получаем короткий ID (последние 8 символов без дефисов)
                short_id = order.get("shortId", "")
                if not short_id:
                    # Берём последние 8 символов ID (без дефисов)
                    clean_id = order_id.replace("-", "")
                    short_id = clean_id[-8:].upper() if len(clean_id) >= 8 else order_id[:8].upper()
                
                # Получаем цену (API возвращает в копейках, конвертируем в рубли)
                # basePrice - ваш доход, totalPrice - сколько заплатил покупатель
                amount_kopecks = order.get("totalPrice") or order.get("basePrice") or order.get("price") or order.get("amount")
                if amount_kopecks is not None:
                    amount = amount_kopecks / 100  # Конвертируем копейки в рубли
                else:
                    amount = 0.0
                    logger.warning(f"Не удалось получить цену для заказа {order_id[:8]}")

                # Debug: логируем все поля цены
                logger.debug(f"Поля цены в заказе {order_id[:8]}: totalPrice={order.get('totalPrice')}, basePrice={order.get('basePrice')} (конвертировано: {amount} ₽)")
                
                # Получаем данные покупателя
                buyer = order.get("user") or {}
                buyer_id = order.get("buyerId")
                buyer_name = "Неизвестно"
                
                if isinstance(buyer, dict):
                    # Извлекаем имя из user объекта
                    buyer_name = (
                        buyer.get("username") or 
                        buyer.get("nickname") or 
                        buyer.get("name") or 
                        buyer.get("displayName") or
                        f"ID{buyer.get('id', buyer_id)}"
                    )
                elif buyer_id:
                    # Fallback: если user отсутствует, используем buyerId
                    buyer_name = f"ID{buyer_id}"
                    # Создаём минимальный user объект для плагинов
                    order["user"] = {
                        "id": buyer_id,
                        "username": buyer_name
                    }
                
                # Получаем данные лота (в Starvell API это offerDetails)
                lot = order.get("offerDetails") or order.get("listing") or order.get("lot") or order.get("offer") or {}
                lot_name = "Неизвестно"
                
                if isinstance(lot, dict):
                    # Для Starvell API: offerDetails.descriptions.rus.briefDescription
                    descriptions = lot.get("descriptions", {})
                    if descriptions:
                        rus_desc = descriptions.get("rus", {})
                        lot_name = (
                            rus_desc.get("briefDescription") or 
                            rus_desc.get("description") or
                            lot.get("name") or 
                            lot.get("title") or
                            "Неизвестно"
                        )
                    else:
                        # Fallback для других форматов
                        lot_name = (
                            lot.get("name") or 
                            lot.get("title") or 
                            lot.get("description") or
                            "Неизвестно"
                        )
                elif isinstance(lot, str):
                    lot_name = lot
                
                # Отправляем уведомление через NotificationManager
                await self.notifier.notify_new_order(
                    order_id=order_id,
                    short_id=short_id,
                    buyer=buyer_name,
                    amount=float(amount),
                    lot_name=lot_name,
                    status=status,
                    order_data=order
                )
                
                # Логируем с полными данными для отладки
                logger.info(f"🛒 Новый заказ #{short_id} от {buyer_name}: {lot_name} - {amount}₽")
                logger.debug(f"Полные данные заказа: {order}")
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке новых заказов: {e}", exc_info=True)
            
    async def _auto_bump(self):
        """Автоматический bump офферов"""
        try:
            # Проверяем, включен ли авто-bump хотя бы у одного админа
            auto_bump_enabled = False
            
            for admin_id in BotConfig.ADMIN_IDS():
                settings = await self.db.get_user_settings(admin_id)
                if settings.get("auto_bump_enabled", False):
                    auto_bump_enabled = True
                    break
                    
            if not auto_bump_enabled:
                return
                
            # Выполняем bump
            logger.info("Выполняется авто-bump офферов...")
            
            result = await self.starvell.bump_offers()
            
            from bot.core import get_notification_manager, NotificationType
            notif_manager = get_notification_manager()
            
            if notif_manager:
                # Уведомляем админов через NotificationManager
                message = f"Время: {datetime.now().strftime('%H:%M:%S')}\n"
                message += f"Game ID: {BotConfig.AUTO_BUMP_GAME_ID()}\n"
                message += f"Категории: {', '.join(map(str, BotConfig.AUTO_BUMP_CATEGORIES()))}"
                
                await notif_manager.notify_all_admins(
                    NotificationType.AUTO_BUMP,
                    message
                )
                        
            logger.info("Авто-bump успешно выполнен")
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении авто-bump: {e}", exc_info=True)

            from bot.core import get_notification_manager
            notif_manager = get_notification_manager()

            # Собираем подробные детали для уведомления (включая конфиг авто-bump)
            details = {
                "Время": datetime.now().strftime('%H:%M:%S'),
                "game_id": BotConfig.AUTO_BUMP_GAME_ID(),
                "categories": BotConfig.AUTO_BUMP_CATEGORIES(),
                "error_type": type(e).__name__,
            }

            # Попытка получить дополнительные аргументы/тело ответа из исключения
            try:
                if hasattr(e, 'args') and e.args:
                    details['args'] = e.args
                # Если исключение содержит вложенные детали (например, словарь), попытаться их добавить
                if hasattr(e, '__dict__'):
                    for k, v in e.__dict__.items():
                        if k not in details:
                            details[k] = str(v)
            except Exception:
                pass

            if notif_manager:
                await notif_manager.notify_error(
                    str(e),
                    context="Авто-bump",
                    details=details
                )
                    
    async def _cleanup_old_data(self):
        """Очистка старых данных"""
        try:
            logger.info("Очистка старых данных...")
            await self.db.cleanup(days=7)

            # Очищаем словарь _seen_messages для предотвращения утечки памяти
            # Оставляем только последние 100 сообщений для каждого чата
            for chat_id in list(self._seen_messages.keys()):
                messages = self._seen_messages[chat_id]
                if len(messages) > 100:
                    # Конвертируем в список, берем последние 100, обратно в set
                    self._seen_messages[chat_id] = set(list(messages)[-100:])
                    logger.debug(f"Очищен кэш сообщений для чата {chat_id}")

            logger.info("Очистка завершена")
        except Exception as e:
            logger.error(f"Ошибка при очистке данных: {e}", exc_info=True)
    
    async def _check_custom_command(self, chat_id: str, message_text: str, author_id: str):
        """Проверить и обработать кастомную команду"""
        try:
            import json
            from pathlib import Path
            
            # Загружаем кастомные команды
            commands_file = Path("storage/custom_commands.json")
            if not commands_file.exists():
                return
            
            with open(commands_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Проверяем, включены ли кастомные команды
            if not data.get("enabled", False):
                return
            
            prefix = data.get("prefix", "!")
            commands = data.get("commands", [])
            
            # Проверяем, начинается ли сообщение с префикса
            if not message_text.startswith(prefix):
                return
            
            # Извлекаем команду (без префикса)
            command_text = message_text[len(prefix):].strip().lower()
            
            # Ищем соответствующую команду
            for cmd in commands:
                if cmd["name"].lower() == command_text:
                    # Нашли команду - отправляем ответ
                    try:
                        await self.starvell.send_message(chat_id, cmd["text"])
                        logger.info(f"🤖 Отправлен автоответ на команду '{prefix}{cmd['name']}' пользователю {author_id}")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке автоответа на команду: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке кастомной команды: {e}", exc_info=True)
    
    async def _check_auto_responses(self):
        """Проверка и отправка автоответов"""
        try:
            if self.auto_response:
                await self.auto_response.check_and_respond()
        except Exception as e:
            logger.error(f"Ошибка при проверке автоответов: {e}", exc_info=True)
            
    async def toggle_auto_bump(self, enabled: bool):
        """Включить/выключить авто-bump"""
        if enabled and not self.scheduler.get_job('auto_bump'):
            self.scheduler.add_job(
                self._auto_bump,
                'interval',
                seconds=BotConfig.AUTO_BUMP_INTERVAL(),
                id='auto_bump',
            )
            logger.info("Авто-bump включен")
        elif not enabled and self.scheduler.get_job('auto_bump'):
            self.scheduler.remove_job('auto_bump')
            logger.info("Авто-bump выключен")

    async def _check_auto_ticket_with_init(self):
        """Первая проверка авто-тикетов при запуске бота"""
        if self._auto_ticket_first_run_done:
            return
        
        self._auto_ticket_first_run_done = True
        logger.info("🎫 Запускаю первую проверку авто-тикетов при старте бота...")
        
        await self._check_auto_ticket_loop()

    async def _check_auto_ticket_loop(self):
        """Проверка авто-тикетов"""
        if not BotConfig.AUTO_TICKET_ENABLED():
            return

        try:
            autoticket = get_autoticket_service()
            if not autoticket:
                logger.warning("Сервис авто-тикетов не инициализирован")
                return

            # Получаем неподтвержденные заказы
            hours = BotConfig.AUTO_TICKET_ORDER_AGE()
            unconfirmed = await autoticket.get_unconfirmed_orders(self.starvell, hours=hours)
            
            if not unconfirmed:
                logger.debug("Неподтверждённых заказов не найдено")
                return
                
            # Убрали лог: 📋 Найдено {len(unconfirmed)} заказов для авто-тикета
            
            # Берём заказы с учётом максимального количества
            max_orders = min(BotConfig.AUTO_TICKET_MAX_ORDERS(), len(unconfirmed))
            orders_to_process = unconfirmed[:max_orders]
            
            # Собираем список ID заказов
            order_ids = [order.get('id') for order in orders_to_process if order.get('id')]
            
            if not order_ids:
                logger.warning("Не удалось извлечь ID заказов")
                return
            
            # Проверяем, можно ли отправить тикет (прошёл ли интервал)
            if not autoticket.can_send_ticket():
                remaining = autoticket.get_time_until_next_ticket()
                logger.info(f"⏳ Тикет не отправлен - интервал не прошёл (осталось {remaining}с)")
                return
            
            # Отправляем ОДИН тикет со ВСЕМИ заказами
            # Первый заказ (самый старый) идёт в поле orderId, остальные в описание
            # Убрали лог: 📨 Создаю тикет с {len(order_ids)} заказами...
            success, msg = await autoticket.send_ticket(order_ids)
            
            # Уведомляем админов о результате (если включено)
            if BotConfig.NOTIFY_AUTO_TICKET() and self.notifier:
                if success:
                    # Формируем список заказов для уведомления (ID в строчку через пробел)
                    orders_list = " ".join([
                        f"#{order.get('id', 'N/A').replace('-', '')[-8:].upper()}"
                        for order in orders_to_process
                    ])
                    
                    text = (
                        f"🎫 <b>Покупатель забыл подтвердить заказ</b>\n\n"
                        f"Список заказов: {orders_list}\n"
                        f"Всего заказов: {len(order_ids)}"
                    )
                    await self.notifier.notify_all_admins(
                        "auto_ticket",
                        text,
                        force=False
                    )
                else:
                    text = (
                        f"❌ <b>Ошибка создания авто-тикета</b>\n\n"
                        f"� Заказов: {len(order_ids)}\n"
                        f"❗ {msg}"
                    )
                    await self.notifier.notify_all_admins(
                        "auto_ticket",
                        text,
                        force=True
                    )
            
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле авто-тикетов: {e}", exc_info=True)
