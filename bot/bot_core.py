"""
Главный файл бота
"""

import asyncio
import logging
import sys
from pathlib import Path
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
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


async def main():
    """Главная функция бота (вызывается из главного main.py)"""
    
    # Валидация конфигурации
    try:
        BotConfig.validate()
        BotConfig.ensure_dirs()
    except ValueError as e:
        logger.error(f"Ошибка конфигурации: {e}")
        logger.error("Проверьте configs/_main.cfg")
        return
        
    
    # Инициализация компонентов
    bot = Bot(
        token=BotConfig.BOT_TOKEN(),
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
    await bot.set_my_commands(commands)
    logger.info("Меню команд установлено")
    
    try:
        await bot.set_my_short_description(
            "🤖 Starvell Cardinal - автоматизация для Starvell.com\n\n📢 Новости: @StarvellCardinal\n🐞 Плагины: @StarvellPlugins"
        )
        
        description = (
            "🔥 Starvell Cardinal - мощный бот для автоматизации работы на Starvell.com\n\n"
            "Контакты:\n"
            "🛠 Автор: @embedium\n"
            "💬 Telegram: @embedium\n"
            "📢 Канал с новостями: @StarvellCardinal\n"
            "🐞 Канал с плагинами: @StarvellPlugins\n"
        )
        await bot.set_my_description(description)
        logger.info("Описание бота установлено")
    except Exception as e:
        logger.warning(f"Не удалось установить описание бота: {e}")
    
    # База данных (JSON хранилище)
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
        await starvell.start()
        # Первичный запрос сразу получает SID и проверяет, что сессия живая.
        # KeepAlive использует этот SID для heartbeat.
        user_info = await starvell.get_user_info()
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
        
        # Обновляем имя бота
        nickname = user.get("nickname") or user.get("username") or "Trader"
        try:
            await bot.set_my_name(f"{nickname} | Starvell Cardinal")
        except Exception as e:
            logger.warning(f"Не удалось изменить имя бота: {e}")
            
        logger.info(f"Авторизован как: {user.get('username')} (ID: {user.get('id')})")
        
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
