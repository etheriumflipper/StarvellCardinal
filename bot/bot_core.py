"""
Главный файл бота
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional
from aiohttp import ClientTimeout
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.core.config import BotConfig, get_config_manager
from bot.core import init_notifications, NotificationType
from bot.core.usage_stats import log_event
from bot.core.storage import Database
from bot.core.services import StarvellService
from bot.handlers import router
from bot.core.middlewares import AuthMiddleware
from bot.features.tasks import BackgroundTasks
from bot.features.auto_delivery import AutoDeliveryService
from bot.features.auto_restore import AutoRestoreService
from bot.features.auto_raise import AutoRaiseService
from bot.features.auto_update import AutoUpdateService
from bot.features.keep_alive import KeepAliveService
from bot.features.auto_response import AutoResponseService
from bot.plugins import PluginManager, init_plugins_cp


logger = logging.getLogger(__name__)

TELEGRAM_TIMEOUT = ClientTimeout(total=30, connect=10, sock_read=20)
TELEGRAM_STARTUP_TIMEOUT = 30


def _create_bot_session(proxy_url: Optional[str]):
    """Создать сессию Telegram с таймаутом, чтобы старт не зависал навсегда."""
    if proxy_url:
        return AiohttpSession(proxy=proxy_url, timeout=TELEGRAM_TIMEOUT)
    return AiohttpSession(timeout=TELEGRAM_TIMEOUT)


async def _telegram_setup(coro, step: str, *, required: bool = False):
    """Выполнить шаг настройки Telegram с таймаутом."""
    try:
        await asyncio.wait_for(coro, timeout=TELEGRAM_STARTUP_TIMEOUT)
        return True
    except asyncio.TimeoutError:
        logger.warning(
            f"⚠️ Таймаут {TELEGRAM_STARTUP_TIMEOUT}s: {step}. "
            "Проверьте интернет или включите Proxy в configs/_main.cfg"
        )
        if required:
            raise
        return False
    except Exception as e:
        logger.warning(f"⚠️ {step}: {e}")
        if required:
            raise
        return False


async def main():
    """Главная функция бота (вызывается из главного main.py)"""
    
    # Валидация конфигурации
    try:
        logger.info("📋 Проверка конфигурации...")
        BotConfig.validate()
        BotConfig.ensure_dirs()
    except ValueError as e:
        logger.error(f"Ошибка конфигурации: {e}")
        logger.error("Проверьте configs/_main.cfg")
        return
        
    
    # Инициализация компонентов
    # Прокси для доступа к Telegram (актуально для РФ и т.п.)
    bot_session = None
    proxy_url = BotConfig.PROXY_URL()
    if proxy_url:
        try:
            bot_session = _create_bot_session(proxy_url)
            _safe = proxy_url
            if '@' in _safe:
                _safe = _safe.split('://', 1)[0] + '://***@' + _safe.split('@', 1)[1]
            logger.info(f"🌐 Подключение к Telegram через прокси: {_safe}")
        except RuntimeError as e:
            logger.error(
                "Не удалось включить прокси: не установлен aiohttp_socks. "
                "Установите: pip install aiohttp_socks"
            )
            logger.error(f"Подробнее: {e}")
            bot_session = None
        except Exception as e:
            logger.error(f"Ошибка инициализации прокси ({e}). Запускаюсь без прокси.")
            bot_session = None

    if bot_session is None:
        bot_session = _create_bot_session(None)

    logger.info("📡 Подключение к Telegram API...")
    bot = Bot(
        token=BotConfig.BOT_TOKEN(),
        session=bot_session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Устанавливаем меню команд
    commands = [
        BotCommand(command="menu", description="🏠 Главное меню"),
        BotCommand(command="profile", description="👤 Профиль продавца"),
        BotCommand(command="update", description="🔄 Обновить бота"),
        BotCommand(command="logs", description="📋 Получить логи"),
        BotCommand(command="restart", description="🔁 Перезапустить бота"),
        BotCommand(command="session_cookie", description="🔑 Обновить session_cookie"),
        BotCommand(command="keepalive", description="🟢 Статус онлайна Starvell"),
    ]
    if await _telegram_setup(bot.set_my_commands(commands), "установка меню команд"):
        logger.info("Меню команд установлено")
    
    try:
        if await _telegram_setup(
            bot.set_my_short_description(
                "🤖 Starvell Cardinal - автоматизация для Starvell.com\n\n📢 Новости: @starvellingbot"
            ),
            "установка краткого описания",
        ):
            description = (
                "🔥 Starvell Cardinal - мощный бот для автоматизации работы на Starvell.com\n\n"
                "Контакты:\n"
                "🛠 Автор: @knowtake\n"
                "💬 Telegram: @knowtake\n"
                "📢 Канал: @starvellingbot\n"
            )
            if await _telegram_setup(bot.set_my_description(description), "установка описания"):
                logger.info("Описание бота установлено")
    except Exception as e:
        logger.warning(f"Не удалось установить описание бота: {e}")
    
    logger.info("💾 Инициализация хранилища...")
    db = Database(storage_dir=BotConfig.STORAGE_DIR())
    await db.connect()
    
    # Сервис Starvell
    starvell = StarvellService(db)
    
    # Инициализация системы уведомлений
    from bot.core import init_notifications
    notifications = init_notifications(bot, starvell)
    logger.info("Система уведомлений инициализирована")
    
    # Сервис авто-выдачи (без зависимостей)
    auto_delivery = AutoDeliveryService()
    
    # Сервис авто-восстановления (требует auto_delivery для проверки товаров)
    auto_restore = AutoRestoreService(starvell, auto_delivery)
    
    # Сервис авто-поднятия
    auto_raise = AutoRaiseService(starvell)
    
    # Сервис автообновления
    auto_update = AutoUpdateService(notifications)
    
    # Сервис вечного онлайна
    keep_alive = KeepAliveService(starvell)
    
    # Сервис автоответов
    auto_response = AutoResponseService(starvell, db)
    
    # Сервис авто-тикетов
    from bot.features.autoticket import init_autoticket_service
    # Получаем сессию напрямую из конфига
    session_cookie = get_config_manager().get('Starvell', 'session_cookie', '')
    autoticket_service = init_autoticket_service(session_cookie)
    
    # Менеджер плагинов
    plugin_manager = PluginManager()
    plugin_manager.load_plugins()
    
    # Устанавливаем plugin_manager в notifications для вызова хэндлеров
    notifications.plugin_manager = plugin_manager
    
    # Инициализируем панель управления плагинами
    init_plugins_cp(bot, plugin_manager, router)
    logger.info("Панель управления плагинами инициализирована")
    
    # Регистрируем хэндлеры плагинов (включая команды)
    plugin_manager.register_handlers(router)
    logger.info("Хэндлеры плагинов зарегистрированы")
    
    try:
        logger.info("🌐 Подключение к Starvell...")
        await starvell.start()
        user_info = await asyncio.wait_for(
            starvell.get_user_info(),
            timeout=30,
        )
        logger.info("✅ Starvell API подключён")
        await auto_delivery.start()
        await auto_restore.start()
        await auto_raise.start()
        await auto_update.start()
        await keep_alive.start()
        await auto_response.start()
        
        # Запускаем хэндлеры инициализации плагинов
        await plugin_manager.run_handlers(plugin_manager.init_handlers, bot, starvell, db, plugin_manager)
        
        # Проверяем авторизацию
        if not user_info.get("authorized"):
            # Не отправляем нотификацию здесь, чтобы не дублировать логику
            # уведомления, уже реализованную в StarvellService._notify_session_error().
            logger.error("Не удалось авторизоваться в Starvell! Продолжаю работу без авторизации.")
            logger.error("Проверьте session_cookie в configs/_main.cfg")
            
        user = user_info.get("user", {})
        
        # Обновляем имя бота (не чаще чем нужно — Telegram flood control)
        nickname = user.get("nickname") or user.get("username") or "Trader"
        desired_name = f"{nickname} | Starvell Cardinal"
        name_cache = Path(BotConfig.STORAGE_DIR()) / "cache" / "bot_display_name.txt"
        name_cache.parent.mkdir(parents=True, exist_ok=True)
        cached_name = name_cache.read_text(encoding="utf-8").strip() if name_cache.exists() else ""
        if cached_name == desired_name:
            logger.debug("Имя бота актуально, пропускаю set_my_name")
        else:
            try:
                if await _telegram_setup(bot.set_my_name(desired_name), "смена имени бота"):
                    name_cache.write_text(desired_name, encoding="utf-8")
            except Exception as e:
                error_text = str(e).lower()
                if "flood control" in error_text or "retry in" in error_text:
                    logger.info("ℹ️ Telegram ограничил смену имени бота — пропускаю до следующего запуска")
                else:
                    logger.warning(f"Не удалось изменить имя бота: {e}")
            
        logger.info(f"Авторизован как: {user.get('username')} (ID: {user.get('id')})")
        
    except asyncio.TimeoutError:
        logger.error("Starvell API не ответил за 30 секунд. Проверьте интернет и session_cookie.")
        logger.exception("Детальная информация об ошибке:")
        await auto_response.stop()
        await keep_alive.stop()
        await auto_update.stop()
        await auto_raise.stop()
        await auto_restore.stop()
        await auto_delivery.stop()
        await starvell.stop()
        await db.close()
        return
    except Exception as e:
        logger.error(f"Ошибка при подключении к Starvell: {e}")
        logger.exception("Детальная информация об ошибке:")
        await auto_response.stop()
        await keep_alive.stop()
        await auto_update.stop()
        await auto_raise.stop()
        await auto_restore.stop()
        await auto_delivery.stop()
        await starvell.stop()
        await db.close()
        return
        
    # Middleware для проверки доступа
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    
    # Регистрируем роутер
    dp.include_router(router)
    
    # Добавляем зависимости в контекст
    dp.workflow_data.update({
        "starvell": starvell,
        "db": db,
        "auto_delivery": auto_delivery,
        "auto_restore": auto_restore,
        "auto_raise": auto_raise,
        "auto_update": auto_update,
        "keep_alive": keep_alive,
        "auto_response": auto_response,
        "autoticket_service": autoticket_service,
        "plugin_manager": plugin_manager,
    })
    
    # Фоновые задачи
    tasks = BackgroundTasks(bot, starvell, db, notifications, auto_response)
    tasks.start()
    
    # Уведомляем админов о запуске
    if BotConfig.NOTIFY_BOT_START():
        try:
            from datetime import datetime
            from version import VERSION
            
            # Формируем детальное уведомление
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            
            message = (
                f"<b>Аккаунт:</b> {user.get('username', 'Неизвестно')}\n"
                f"<b>ID:</b> <code>{user.get('id', 'N/A')}</code>\n\n"
                f"<b>Версия бота:</b> <code>{VERSION}</code>\n"
                f"<b>Время запуска:</b> <code>{current_time}</code>\n\n"
            )
            
            await notifications.notify_all_admins(
                NotificationType.BOT_STARTED,
                message,
                force=False
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление о запуске: {e}")
            
        logger.info("✅ Бот успешно запущен!")
        # Записываем событие в usage_stats
        try:
            from version import VERSION
            log_event("bot_started", f"version={VERSION} user={user.get('username')} id={user.get('id')} time={current_time}")
        except Exception:
            log_event("bot_started", f"user={user.get('username')} id={user.get('id')} time={current_time}")
    
    # Запускаем хэндлеры старта плагинов
    await plugin_manager.run_handlers(plugin_manager.start_handlers, bot, starvell, db, plugin_manager)
    
    try:
        # Запускаем polling
        await dp.start_polling(bot)
    finally:
        # Очистка
        logger.info("Остановка бота...")
        
        # Запускаем хэндлеры остановки плагинов
        await plugin_manager.run_handlers(plugin_manager.stop_handlers, bot, starvell, db, plugin_manager)
        
        tasks.stop()
        await keep_alive.stop()
        await auto_update.stop()
        await auto_raise.stop()
        await auto_restore.stop()
        await auto_delivery.stop()
        await starvell.stop()
        await db.close()
        
        
        # Логируем остановку
        try:
            log_event("bot_stopped", "clean shutdown")
        except Exception:
            pass
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
