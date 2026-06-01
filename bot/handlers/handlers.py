"""
Обработчики команд бота
"""

import asyncio
import hashlib
import html
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.core.config import BotConfig, get_config_manager
from bot.keyboards import (
    get_main_menu,
    get_global_switches_menu,
    get_notifications_menu,
    get_auto_delivery_lots_menu,
    get_auto_ticket_settings_menu,
    get_proxy_menu,
    get_blacklist_menu,
    get_plugins_menu,
    get_select_template_menu,
    get_custom_commands_menu,
    CBT,
)
from bot.handlers import auto_delivery_handlers, blacklist_handlers, plugins_handlers, templates_handlers, extra_handlers, custom_commands_handlers, welcome_handlers


router = Router()
router.include_router(auto_delivery_handlers.router)
router.include_router(blacklist_handlers.router)
router.include_router(plugins_handlers.router)
router.include_router(templates_handlers.router)
router.include_router(extra_handlers.router)
router.include_router(custom_commands_handlers.router)
router.include_router(welcome_handlers.router)


# Утилита: безопасное приведение к float (чтобы избежать ошибок форматирования, если приходит dict)
def _safe_float(val, default=0.0):
    """Преобразовать в float безопасно; в случае ошибки вернуть default"""
    try:
        if isinstance(val, dict):
            for k in ("amount", "price", "totalPrice", "basePrice", "value"):
                if k in val:
                    try:
                        return float(val[k])
                    except Exception:
                        continue
            return default
        return float(val)
    except Exception:
        return default


def _format_keepalive_age(monotonic_time):
    if not monotonic_time:
        return "нет"

    age = int(asyncio.get_event_loop().time() - monotonic_time)
    if age < 0:
        age = 0
    if age < 60:
        return f"{age} сек назад"
    if age < 3600:
        return f"{age // 60} мин назад"
    return f"{age // 3600} ч {(age % 3600) // 60} мин назад"


# === Состояния ===

class AuthState(StatesGroup):
    """Состояния для авторизации"""
    waiting_for_password = State()


class ReplyState(StatesGroup):
    """Состояния для быстрого ответа на сообщения"""
    waiting_for_reply = State()


class SessionState(StatesGroup):
    """Состояния для обновления session_cookie"""
    waiting_for_cookie = State()


class ProxyState(StatesGroup):
    """Состояния для настройки прокси Telegram"""
    waiting_for_addr = State()
    waiting_for_auth = State()


class AutoTicketState(StatesGroup):
    """Состояния для настройки авто-тикетов"""
    waiting_for_interval = State()
    waiting_for_max_orders = State()


# === Функции авторизации ===

def hash_password(password: str) -> str:
    """Хеширование пароля"""
    return hashlib.sha256(password.encode()).hexdigest()


def is_user_authorized(user_id: int) -> bool:
    """Проверка авторизации пользователя"""
    admin_ids = BotConfig.ADMIN_IDS()
    return user_id in admin_ids


async def authorize_user(user_id: int):
    """Добавить пользователя в список админов"""
    admin_ids = BotConfig.ADMIN_IDS()
    if user_id not in admin_ids:
        admin_ids.append(user_id)
        BotConfig.set_admin_ids(admin_ids)

# === Команды ===

@router.message(Command("start"))
@router.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext, auto_update, **kwargs):
    """Команда /start"""
    # Загружаем текущий язык
    
    
    # Проверяем авторизацию
    if not is_user_authorized(message.from_user.id):
        # Показываем приглашение ввести пароль и кнопку с ссылкой на репозиторий
        try:
            repo_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="Хочу такого же бота",
                    url="https://t.me/embedium"
                )]
            ])
            await message.answer("🔒 Для доступа к боту введите пароль:", reply_markup=repo_kb)
        except Exception:
            # На случай редких проблем со сборкой клавиатуры просто отправим текст
            await message.answer("🔒 Для доступа к боту введите пароль:")

        await state.set_state(AuthState.waiting_for_password)
        return
    
    # Проверяем наличие обновлений
    update_available = auto_update.update_available if auto_update else False
    
    await message.answer(
        "🌟 <b>Starvell Cardinal</b>\n\nПривет! Я помогу управлять вашим магазином на Starvell.\n\nИспользуйте меню ниже для управления ботом.",
        reply_markup=get_main_menu(update_available=update_available)
    )


@router.message(Command("update"))
async def cmd_update(message: Message, auto_update, **kwargs):
    """Команда /update - обновить бот"""
    # Проверяем авторизацию
    if not is_user_authorized(message.from_user.id):
        return
    
    # Проверяем наличие обновлений
    status_msg = await message.answer("🔍 Проверка обновлений...")
    
    update_available = await auto_update.check_for_updates()
    
    if not update_available:
        await status_msg.edit_text(
            f"✅ Установлена последняя версия: <code>{auto_update.current_version}</code>"
        )
        return
    
    # Обновление доступно
    await status_msg.edit_text(
        f"✨ Доступно обновление!\n\n"
        f"📌 Текущая: <code>{auto_update.current_version}</code>\n"
        f"✨ Новая: <code>{auto_update.latest_version}</code>\n\n"
        f"🔄 Начинаю обновление..."
    )
    
    # Выполняем обновление
    result = await auto_update.perform_update()
    safe_message = html.escape(result.get("message", ""))
    safe_output = html.escape(result.get("output", ""))
    
    if result["success"]:
        # Сбрасываем флаг уведомления после успешного обновления
        auto_update.reset_notification_flag()
        
        await status_msg.edit_text(
            safe_message + "\n\n"
            f"<tg-spoiler>Git output:\n{safe_output}</tg-spoiler>\n\n"
            f"🔄 Перезапуск бота через 3 секунды..."
        )
        
        # Даём время прочитать сообщение и перезапускаем бот
        await asyncio.sleep(3)
        
        import os
        import sys
        os.execv(sys.executable, [sys.executable] + sys.argv)
    else:
        await status_msg.edit_text(
            safe_message + "\n\n"
            f"<tg-spoiler>Error:\n{safe_output}</tg-spoiler>"
        )


@router.message(Command("check_update"))
@router.message(Command("check_updates"))
async def cmd_check_update(message: Message, auto_update, **kwargs):
    """Команда /check_update(/s) - проверить наличие обновлений вручную"""
    if not is_user_authorized(message.from_user.id):
        return

    status_msg = await message.answer("🔍 Проверка обновлений...")

    update_available = await auto_update.check_for_updates()

    if update_available:
        await status_msg.edit_text(
            f"✨ <b>Доступно обновление!</b>\n\n"
            f"📌 Текущая версия: <code>{auto_update.current_version}</code>\n"
            f"✨ Новая версия: <code>{auto_update.latest_version}</code>\n\n"
            f"Чтобы установить — отправьте /update"
        )
    else:
        await status_msg.edit_text(
            f"✅ Установлена последняя версия: <code>{auto_update.current_version}</code>"
        )


@router.message(Command("session_cookie"))
async def cmd_session_cookie(message: Message, starvell, **kwargs):
    """Команда /session_cookie <cookie> — обновить session_cookie и перезапустить подключение к Starvell"""
    # Проверяем авторизацию
    if not is_user_authorized(message.from_user.id):
        return

    # Разрешаем ввод в том же сообщении: /session_cookie <value>
    parts = message.text.split(None, 1)
    if len(parts) == 1:
        # Запускаем FSM — ждём, пока пользователь отправит новый ключ в следующем сообщении
        await message.answer(
            "✉️ Отправьте новый <b>session_cookie</b> сообщением в этом чате.\n\n"
            "Для отмены отправьте /cancel",
            parse_mode="HTML"
        )
        await message.answer(
            "ℹ️ Примечание: рекомендуется отправлять ключ в личном чате с ботом, чтобы он не оказался в групповой переписке."
        )
        await message.answer("⏳ Жду новый session_cookie...")
        await kwargs.get('state').set_state(SessionState.waiting_for_cookie)
        return

    new_cookie = parts[1].strip()
    if not new_cookie:
        await message.answer("❌ Пустое значение session_cookie. Попробуйте ещё раз.")
        return

    # Сохраняем в конфиг
    try:
        config = get_config_manager()
        config.set('Starvell', 'session_cookie', new_cookie)
        # Применяем изменения в рантайме
        BotConfig.reload()
    except Exception as e:
        await message.answer(f"❌ Не удалось сохранить конфигурацию: {e}")
        return

    await message.answer("✅ session_cookie обновлён в конфиге. Попытка перезапустить подключение к Starvell...")

    # Перезапускаем StarvellService (если он доступен через injected dependency)
    try:
        # starvell — это экземпляр StarvellService, прокинутый в workflow_data
        await starvell.stop()
        await starvell.start()
        # После старта флаг _session_error_notified уже сброшен в start()
        # Проверяем авторизацию
        user_info = await starvell.get_user_info()
        if user_info.get('authorized'):
            await message.answer("✅ Успешно авторизован в Starvell. Все службы могут продолжить работу.")
        else:
            await message.answer("⚠️ Перезапуск выполнен, но авторизация не удалась. Проверьте session_cookie и при необходимости перезапустите бота вручную.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при перезапуске сервиса Starvell: {e}")
        import logging
        logging.getLogger(__name__).exception("Ошибка при перезапуске StarvellService")



@router.message(SessionState.waiting_for_cookie)
async def process_session_cookie_input(message: Message, state: FSMContext, starvell=None, **kwargs):
    """Обработка введённого session_cookie из FSM"""
    # Только авторизованный админ может вводить
    if not is_user_authorized(message.from_user.id):
        await message.answer("🔒 Только администратор может обновлять session_cookie")
        await state.clear()
        return

    new_cookie = (message.text or "").strip()
    if not new_cookie:
        await message.answer("❌ Пустой ключ. Отправьте /session_cookie и попробуйте снова.")
        await state.clear()
        return

    await message.answer("🔁 Сохраняю новый ключ и перезапускаю подключение...")

    try:
        config = get_config_manager()
        config.set('Starvell', 'session_cookie', new_cookie)
        BotConfig.reload()

        if starvell:
            await starvell.stop()
            await starvell.start()

            # Проверяем авторизацию
            user_info = await starvell.get_user_info()
            if user_info.get('authorized'):
                await message.answer("✅ Ключ успешно обновлён и авторизация выполнена.")
            else:
                await message.answer("⚠️ Ключ сохранён, но авторизация не удалась. Проверьте значение session_cookie.")
        else:
            await message.answer("✅ Ключ сохранён в конфиге. Перезапустите бота вручную для применения.")

    except Exception as e:
        await message.answer(f"❌ Ошибка при обновлении ключа: {e}")
        import logging
        logging.getLogger(__name__).exception("Ошибка при обновлении session_cookie")

    await state.clear()


@router.message(Command("profile"))
async def cmd_profile(message: Message, starvell, **kwargs):
    """Команда /profile - показать профиль продавца"""
    # Проверяем авторизацию
    if not is_user_authorized(message.from_user.id):
        return
    
    try:
        # Получаем информацию о пользователе
        user_info = await starvell.get_user_info()
        
        if not user_info.get("authorized"):
            await message.answer("❌ Не авторизован в Starvell")
            return
        
        user_data = user_info.get("user", {})
        
        # Формируем информацию о профиле
        username = user_data.get("username", "Неизвестно")
        user_id = user_data.get("id", "?")
        
        # Баланс может быть числом или словарем, безопасно извлекаем
        balance_raw = user_data.get("balance", 0)
        balance = balance_raw if isinstance(balance_raw, (int, float)) else 0
        
        hold_balance_raw = user_data.get("holdBalance", 0)
        hold_balance = hold_balance_raw if isinstance(hold_balance_raw, (int, float)) else 0
        
        total_balance = balance + hold_balance
        
        # Получаем статус верификации
        verified = "✅ Верифицирован" if user_data.get("verified") else "❌ Не верифицирован"
        
        # Получаем дату регистрации
        created_at = user_data.get("createdAt", "Неизвестно")
        if created_at != "Неизвестно":
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                created_at = dt.strftime("%d.%m.%Y %H:%M")
            except:
                pass
        
        # Рейтинг и отзывы
        rating = user_data.get("rating", 0)
        reviews_count = user_data.get("reviewsCount", 0)
        
        text = f"👤 <b>Профиль продавца</b>\n\n"
        text += f"<b>Имя:</b> {username}\n"
        text += f"<b>ID:</b> <code>{user_id}</code>\n"
        text += f"<b>Статус:</b> {verified}\n"
        text += f"<b>Регистрация:</b> {created_at}\n\n"
        text = f"💰 <b>Баланс:</b>\n"
        text += f"├ Доступно: <code>{_safe_float(balance):.2f}</code> ₽\n"
        text += f"├ Заморожено: <code>{_safe_float(hold_balance):.2f}</code> ₽\n"
        text += f"└ Всего: <code>{_safe_float(total_balance):.2f}</code> ₽\n\n"
        text += f"⭐ <b>Рейтинг:</b> {_safe_float(rating):.1f} ({reviews_count} отзывов)"

        # Кнопка для статистики
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📊 Подробная статистика",
                callback_data="profile_stats"
            )],
            [InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data="profile_refresh"
            )]
        ])

    # Балансы уже форматированы безопасно выше, замены не требуются

        await message.answer(text, reply_markup=keyboard)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при получении профиля: {e}")


@router.callback_query(F.data == "profile_refresh")
async def callback_profile_refresh(callback: CallbackQuery, starvell, **kwargs):
    """Обновить информацию о профиле"""
    await callback.answer("🔄 Обновление...")
    
    try:
        # Получаем информацию о пользователе
        user_info = await starvell.get_user_info()
        
        if not user_info.get("authorized"):
            await callback.message.edit_text("❌ Не авторизован в Starvell")
            return
        
        user_data = user_info.get("user", {})
        
        # Формируем информацию о профиле
        username = user_data.get("username", "Неизвестно")
        user_id = user_data.get("id", "?")
        
        # Баланс может быть числом или словарем, безопасно извлекаем
        balance_raw = user_data.get("balance", 0)
        balance = balance_raw if isinstance(balance_raw, (int, float)) else 0
        
        hold_balance_raw = user_data.get("holdBalance", 0)
        hold_balance = hold_balance_raw if isinstance(hold_balance_raw, (int, float)) else 0
        
        total_balance = balance + hold_balance
        
        # Получаем статус верификации
        verified = "✅ Верифицирован" if user_data.get("verified") else "❌ Не верифицирован"
        
        # Получаем дату регистрации
        created_at = user_data.get("createdAt", "Неизвестно")
        if created_at != "Неизвестно":
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                created_at = dt.strftime("%d.%m.%Y %H:%M")
            except:
                pass
        
        # Рейтинг и отзывы
        rating = user_data.get("rating", 0)
        reviews_count = user_data.get("reviewsCount", 0)
        
        text = f"👤 <b>Профиль продавца</b>\n\n"
        text += f"<b>Имя:</b> {username}\n"
        text += f"<b>ID:</b> <code>{user_id}</code>\n"
        text += f"<b>Статус:</b> {verified}\n"
        text += f"<b>Регистрация:</b> {created_at}\n\n"
        text += f"💰 <b>Баланс:</b>\n"
        text += f"├ Доступно: <code>{_safe_float(balance):.2f}</code> ₽\n"
        text += f"├ Заморожено: <code>{_safe_float(hold_balance):.2f}</code> ₽\n"
        text += f"└ Всего: <code>{_safe_float(total_balance):.2f}</code> ₽\n\n"
        text += f"⭐ <b>Рейтинг:</b> {rating:.1f} ({reviews_count} отзывов)"
        
        # Кнопка для статистики
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📊 Подробная статистика",
                callback_data="profile_stats"
            )],
            [InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data="profile_refresh"
            )]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data == "profile_stats")
async def callback_profile_stats(callback: CallbackQuery, starvell, **kwargs):
    """Показать подробную статистику"""
    await callback.answer("📊 Загрузка статистики...")
    
    try:
        # Получаем заказы
        orders = await starvell.get_orders()
        
        # Анализируем статистику (проверка регистра статуса)
        total_orders = len(orders)
        completed_orders = sum(1 for order in orders if str(order.get("status")).upper() == "COMPLETED")
        cancelled_orders = sum(1 for order in orders if str(order.get("status")).upper() == "CANCELLED")
        active_orders = total_orders - completed_orders - cancelled_orders
        
        # Считаем доход (ключ basePrice)
        total_income = sum(order.get("basePrice", 0) for order in orders if str(order.get("status")).upper() == "COMPLETED")
        
        # Считаем среднюю оценку
        reviews = [order.get("review", {}) for order in orders if order.get("review")]
        avg_rating = sum(r.get("rating", 0) for r in reviews) / len(reviews) if reviews else starvell.last_user_info.get("user", {}).get("rating", 0)
        
        # Статистика по датам
        from datetime import datetime, timedelta
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)
        
        orders_today = 0
        orders_week = 0
        orders_month = 0
        income_today = 0
        income_week = 0
        income_month = 0
        
        for order in orders:
            if order.get("status") != "completed":
                continue
                
            created_at = order.get("createdAt")
            if not created_at:
                continue
                
            try:
                order_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                order_price = order.get("basePrice", 0)
                
                if order_date >= today_start:
                    orders_today += 1
                    income_today += order_price
                    
                if order_date >= week_start:
                    orders_week += 1
                    income_week += order_price
                    
                if order_date >= month_start:
                    orders_month += 1
                    income_month += order_price
            except:
                continue
        
        text = f"📊 <b>Подробная статистика</b>\n\n"
        text += f"📦 <b>Заказы:</b>\n"
        text += f"├ Всего: <code>{total_orders}</code>\n"
        text += f"├ Завершено: <code>{completed_orders}</code> ({completed_orders/total_orders*100 if total_orders else 0:.1f}%)\n"
        text += f"├ Активных: <code>{active_orders}</code>\n"
        text += f"└ Отменено: <code>{cancelled_orders}</code>\n\n"
        
        text += f"💰 <b>Доход (завершенные):</b>\n"
        text += f"├ За сегодня: <code>{_safe_float(income_today):.2f}</code> ₽ ({orders_today} зак.)\n"
        text += f"├ За неделю: <code>{_safe_float(income_week):.2f}</code> ₽ ({orders_week} зак.)\n"
        text += f"├ За месяц: <code>{_safe_float(income_month):.2f}</code> ₽ ({orders_month} зак.)\n"
        text += f"└ Всего: <code>{_safe_float(total_income):.2f}</code> ₽\n\n"
        
        text += f"⭐ <b>Отзывы:</b>\n"
        text += f"├ Средняя оценка: <code>{_safe_float(avg_rating):.2f}</code>\n"
        text += f"└ Всего отзывов: <code>{len(reviews)}</code>\n\n"
        
        if total_orders > 0:
            avg_order_value = _safe_float(total_income) / completed_orders if completed_orders else 0
            text += f"📈 <b>Средний чек:</b> <code>{_safe_float(avg_order_value):.2f}</code> ₽"
        
        # Кнопки управления
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="� Обновить статистику",
                callback_data="profile_stats"
            )],
            [InlineKeyboardButton(
                text="� Вернуться к профилю",
                callback_data="profile_back"
            )]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data == "profile_back")
async def callback_profile_back(callback: CallbackQuery, starvell, **kwargs):
    """Вернуться к профилю"""
    await callback.answer()
    
    # Получаем информацию о пользователе
    user_info = await starvell.get_user_info()
    
    if not user_info.get("authorized"):
        await callback.answer("❌ Не авторизован", show_alert=True)
        return
    
    user = user_info.get("user", {})
    username = user.get("username", "Неизвестно")
    user_id = user.get("id", "N/A")
    # Получаем баланс корректно
    balance_data = user.get("balance", {})
    balance = balance_data.get("rubBalance", 0) if isinstance(balance_data, dict) else 0
    hold_balance = user.get("holdedAmount", 0)
    
    # Статус верификации (KYC)
    verified = "✅ Верифицирован" if user.get("kycStatus") == "VERIFIED" else "❌ Не верифицирован"
    
    # Регистрация
    created_at = user.get("createdAt", "Неизвестно")
    if created_at != "Неизвестно":
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            created_at = dt.strftime("%d.%m.%Y %H:%M")
        except:
            pass
    
    # Получаем статистику
    orders = await starvell.get_orders()
    total_orders = len(orders)
    active_orders = sum(1 for o in orders if str(o.get("status")).upper() not in ["COMPLETED", "CANCELLED"])
    
    # Статистика по отзывам
    reviews = [o.get("review") for o in orders if o.get("review")]
    # Если нет отзывов по заказам, берем общий рейтинг из профиля
    if reviews:
        avg_rating = sum(r.get("rating", 0) for r in reviews) / len(reviews)
    else:
        avg_rating = user.get("rating", 0)
    
    text = f"👤 <b>Профиль</b>\n\n"
    text += f"<b>Имя:</b> {username}\n"
    text += f"<b>ID:</b> <code>{user_id}</code>\n"
    text += f"<b>Статус:</b> {verified}\n"
    text += f"<b>Регистрация:</b> {created_at}\n\n"
    text += f"💰 <b>Баланс:</b>\n"
    text += f"├ Доступно: <code>{_safe_float(balance):.2f}</code> ₽\n"
    text += f"├ Заморожено: <code>{_safe_float(hold_balance):.2f}</code> ₽\n"
    text += f"└ Всего: <code>{_safe_float(balance + hold_balance):.2f}</code> ₽\n\n"
    text += f"📦 <b>Заказы:</b>\n"
    text += f"├ Всего: <code>{total_orders}</code>\n"
    text += f"⭐ <b>Средняя оценка:</b> <code>{avg_rating:.2f}</code>"
    
    # Кнопки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📊 Подробная статистика",
            callback_data="profile_stats"
        )],
        [InlineKeyboardButton(
            text="🔄 Обновить",
            callback_data="profile_refresh"
        )],
        [InlineKeyboardButton(
            text="🔙 Назад",
            callback_data=CBT.MAIN
        )]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.message(Command("keepalive"))
@router.message(lambda message: (message.text or "").strip().lower().startswith("keepalive"))
async def cmd_keepalive(message: Message, keep_alive=None, starvell=None, **kwargs):
    """KeepAlive status and manual actions."""
    if not is_user_authorized(message.from_user.id):
        return

    if keep_alive is None:
        await message.answer("❌ KeepAlive не найден в контексте бота. Обнови bot_core.py и перезапусти бота.")
        return

    text_parts = (message.text or "").strip().split()
    action = text_parts[1].lower() if len(text_parts) > 1 else ""

    action_result = ""
    if action in ("reconnect", "restart", "r"):
        ok = await keep_alive.restart_online_socket()
        await asyncio.sleep(2)
        action_result = "🔄 Websocket переподключён" if ok else "⛔ KeepAlive выключен в конфиге"
    elif action in ("ping", "check", "p"):
        ok = await keep_alive.force_http_check()
        action_result = "✅ HTTP heartbeat прошёл" if ok else "⚠️ HTTP heartbeat не прошёл"

    status = keep_alive.get_status()
    now = asyncio.get_event_loop().time()
    socket_last = status.get("last_socket_success")
    http_last = status.get("last_success")
    socket_fresh = bool(socket_last and now - socket_last < 90)

    sid_present = "нет"
    authorized = "не проверено"
    username = "-"
    auth_error = ""

    if starvell is not None:
        try:
            api = getattr(starvell, "api", None)
            session = getattr(api, "session", None)
            if session and session.get_sid():
                sid_present = "да"
        except Exception:
            sid_present = "ошибка проверки"

        try:
            user_info = await asyncio.wait_for(starvell.get_user_info(), timeout=10)
            authorized = "да" if user_info.get("authorized") else "нет"
            user = user_info.get("user") or {}
            username = user.get("username") or user.get("nickname") or "-"
        except Exception as e:
            authorized = "ошибка"
            auth_error = str(e)

        try:
            api = getattr(starvell, "api", None)
            session = getattr(api, "session", None)
            if session and session.get_sid():
                sid_present = "да"
        except Exception:
            pass

    lines = [
        "🟢 <b>KeepAlive Starvell</b>",
        "",
        f"<b>Сервис:</b> {'включён' if status.get('enabled') else 'выключен'} / {'запущен' if status.get('running') else 'остановлен'}",
        f"<b>Online websocket:</b> {'живой' if socket_fresh else 'нет свежего подтверждения'}",
        f"<b>Namespaces:</b> <code>{html.escape(', '.join(status.get('connected_namespaces') or []) or '-')}</code>",
        f"<b>Последний websocket:</b> {_format_keepalive_age(socket_last)}",
        f"<b>Последний HTTP:</b> {_format_keepalive_age(http_last)}",
        f"<b>Ошибок websocket подряд:</b> <code>{status.get('socket_fail_count', 0)}</code>",
        f"<b>Ошибок HTTP подряд:</b> <code>{status.get('fail_count', 0)}</code>",
        "",
        f"<b>Starvell authorized:</b> {authorized}",
        f"<b>SID:</b> {sid_present}",
        f"<b>Аккаунт:</b> <code>{html.escape(str(username))}</code>",
    ]

    if action_result:
        lines.insert(2, action_result)
        lines.insert(3, "")

    if auth_error:
        lines.extend(["", f"<b>Ошибка авторизации:</b> <code>{html.escape(auth_error[:500])}</code>"])

    if status.get("last_socket_error"):
        lines.extend(["", f"<b>Socket error:</b> <code>{html.escape(str(status['last_socket_error'])[:500])}</code>"])

    if status.get("last_socket_packet"):
        lines.append(f"<b>Last packet:</b> <code>{html.escape(str(status['last_socket_packet'])[:500])}</code>")

    lines.extend([
        "",
        "<code>/keepalive ping</code> - разовый HTTP check",
        "<code>/keepalive reconnect</code> - переподключить websocket",
    ])

    await message.answer("\n".join(lines))


@router.message(Command("logs"))
async def cmd_logs(message: Message, **kwargs):
    """Команда /logs - отправить логи"""
    # Проверяем авторизацию
    if not is_user_authorized(message.from_user.id):
        return
    
    from pathlib import Path
    from aiogram.types import FSInputFile, BufferedInputFile
    
    log_file = Path("logs/bot.log")
    
    # Проверяем существование файла
    if not log_file.exists():
        await message.answer("❌ Файл логов не найден")
        return
    
    try:
        # Читаем последние ошибки из лога
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Ищем последнюю ошибку
        last_error = None
        error_lines = []
        
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]
            if ' - ERROR - ' in line or ' [E] ' in line:
                # Нашли ошибку, собираем её и следующие строки (traceback)
                error_lines = []
                for j in range(i, min(i + 20, len(lines))):
                    error_lines.append(lines[j])
                    if j > i and (' - INFO - ' in lines[j] or ' [I] ' in lines[j] or ' - WARNING - ' in lines[j] or ' [W] ' in lines[j]):
                        break
                last_error = ''.join(error_lines)
                break
        
        # Формируем сообщение
        if last_error:
            error_msg = f"📋 <b>Последняя ошибка:</b>\n\n<code>{last_error[:3500]}</code>"
        else:
            error_msg = "✅ Ошибок не обнаружено"
        
        # Отправляем сообщение с краткой информацией об ошибке
        await message.answer(error_msg)
        # Отправим полный лог-файл как документ
        await message.answer_document(
            FSInputFile(str(log_file)),
            caption="📄 Полный лог-файл бота"
        )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при чтении логов: {e}")


@router.message(Command("restart"))
async def cmd_restart(message: Message, **kwargs):
    """Команда /restart - перезапустить бот"""
    # Проверяем авторизацию
    if not is_user_authorized(message.from_user.id):
        return
    
    import os
    import sys
    
    await message.answer(
        "🔄 <b>Перезапуск бота...</b>\n\n"
        "⏳ Бот будет перезапущен через несколько секунд"
    )
    
    # Даём время отправить сообщение
    await asyncio.sleep(1)
    
    # Перезапускаем процесс
    os.execv(sys.executable, [sys.executable] + sys.argv)


@router.message(AuthState.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    """Обработка ввода пароля"""
    password = message.text
    password_hash = hash_password(password)
    stored_hash = BotConfig.PASSWORD_HASH()
    
    # Удаляем сообщение с паролем
    try:
        await message.delete()
    except:
        pass
    
    if password_hash == stored_hash:
        # Пароль верный - авторизуем пользователя
        await authorize_user(message.from_user.id)
        await state.clear()
        
        await message.answer(
            "✅ Авторизация успешна!" + "\n\n" + "🌟 <b>Starvell Cardinal</b>\n\nПривет! Я помогу управлять вашим магазином на Starvell.\n\nИспользуйте меню ниже для управления ботом.",
            reply_markup=get_main_menu()
        )
    else:
        # Пароль неверный
        await message.answer("❌ Неверный пароль. Попробуйте ещё раз:")


# === Callback обработчики ===

@router.callback_query(F.data == "update_now")
async def callback_update_now(callback: CallbackQuery, auto_update, **kwargs):
    """Обработчик кнопки 'Обновить сейчас'"""
    await callback.answer()
    
    # Редактируем сообщение, показываем процесс
    try:
        # Выполняем обновление
        result = await auto_update.perform_update()
        safe_message = html.escape(result.get("message", ""))
        safe_output = html.escape(result.get("output", ""))
        
        if result["success"]:
            # Сбрасываем флаг уведомления после успешного обновления
            auto_update.reset_notification_flag()
            
            response = (
                f"{safe_message}\n\n"
                f"<tg-spoiler>Git output:\n{safe_output}</tg-spoiler>\n\n"
                f"🔄 Перезапуск бота через 3 секунды..."
            )
            await callback.message.edit_text(response, parse_mode="HTML")
            
            # Даём время прочитать сообщение и перезапускаем бот
            await asyncio.sleep(3)
            
            import os
            import sys
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            response = (
                f"{safe_message}\n\n"
                f"<tg-spoiler>Error:\n{safe_output}</tg-spoiler>"
            )
            await callback.message.edit_text(response, parse_mode="HTML")
    except Exception as e:
        safe_error = html.escape(str(e))
        response = f"❌ <b>Ошибка при обновлении:</b>\n{safe_error}"
        await callback.message.edit_text(response, parse_mode="HTML")


@router.callback_query(F.data == CBT.MAIN)
async def callback_main_menu(callback: CallbackQuery, auto_update, **kwargs):
    """Главное меню"""
    await callback.answer()
    
    # Загружаем текущий язык
    
    # Проверяем наличие обновлений
    update_available = auto_update.update_available if auto_update else False
    
    await callback.message.edit_text(
        "🌟 <b>Starvell Cardinal</b>\n\nПривет! Я помогу управлять вашим магазином на Starvell.\n\nИспользуйте меню ниже для управления ботом.",
        reply_markup=get_main_menu(update_available=update_available)
    )


@router.callback_query(F.data == CBT.GLOBAL_SWITCHES)
async def callback_global_switches(callback: CallbackQuery):
    """Меню глобальных переключателей"""
    await callback.answer()
    
    # Загружаем текущий язык
    
    
    # Получаем текущие настройки
    auto_bump = BotConfig.AUTO_BUMP_ENABLED()
    auto_delivery = BotConfig.AUTO_DELIVERY_ENABLED()
    auto_restore = BotConfig.AUTO_RESTORE_ENABLED()
    auto_read = BotConfig.AUTO_READ_ENABLED()
    auto_ticket = BotConfig.AUTO_TICKET_ENABLED()
    auto_install = BotConfig.AUTO_UPDATE_INSTALL()
    order_confirm = BotConfig.ORDER_CONFIRM_RESPONSE_ENABLED()
    review_response = BotConfig.REVIEW_RESPONSE_ENABLED()
    
    # Формируем описание
    status_text = "⚙️ <b>Глобальные переключатели</b>\n\nЗдесь вы можете включать и отключать основные функции бота.\n\n"
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_global_switches_menu(auto_bump, auto_delivery, auto_restore, auto_read, auto_ticket, auto_install, order_confirm, review_response)
    )


@router.callback_query(F.data == CBT.SWITCH_AUTO_BUMP)
async def callback_switch_auto_bump(callback: CallbackQuery, auto_raise=None, **kwargs):
    """Переключить авто-поднятие"""
    # Переключаем
    current = BotConfig.AUTO_BUMP_ENABLED()
    BotConfig.update(**{"auto_bump.enabled": not current})
    
    # Если включили - триггерим немедленную проверку
    if not current and auto_raise:
        await auto_raise.trigger_immediate_check()
    
    # Загружаем текущий язык
    
    
    # Уведомление об изменении
    status = "включено" if not current else "выключено"
    await callback.answer(f"Авто-поднятие {status}", show_alert=False)
    
    # Обновляем меню
    auto_bump = not current
    auto_delivery = BotConfig.AUTO_DELIVERY_ENABLED()
    auto_restore = BotConfig.AUTO_RESTORE_ENABLED()
    auto_read = BotConfig.AUTO_READ_ENABLED()
    auto_ticket = BotConfig.AUTO_TICKET_ENABLED()
    auto_install = BotConfig.AUTO_UPDATE_INSTALL()
    order_confirm = BotConfig.ORDER_CONFIRM_RESPONSE_ENABLED()
    review_response = BotConfig.REVIEW_RESPONSE_ENABLED()
    
    status_text = "⚙️ <b>Глобальные переключатели</b>\n\nЗдесь вы можете включать и отключать основные функции бота."
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_global_switches_menu(auto_bump, auto_delivery, auto_restore, auto_read, auto_ticket, auto_install, order_confirm, review_response)
    )


@router.callback_query(F.data == CBT.SWITCH_AUTO_DELIVERY)
async def callback_switch_auto_delivery(callback: CallbackQuery):
    """Переключить авто-выдачу"""
    # Переключаем
    current = BotConfig.AUTO_DELIVERY_ENABLED()
    BotConfig.update(**{"auto_delivery.enabled": not current})
    
    # Загружаем текущий язык
    
    
    # Уведомление об изменении
    status = "включена" if not current else "выключена"
    await callback.answer(f"Авто-выдача {status}", show_alert=False)
    
    # Обновляем меню
    auto_bump = BotConfig.AUTO_BUMP_ENABLED()
    auto_delivery = not current
    auto_restore = BotConfig.AUTO_RESTORE_ENABLED()
    auto_read = BotConfig.AUTO_READ_ENABLED()
    auto_ticket = BotConfig.AUTO_TICKET_ENABLED()
    auto_install = BotConfig.AUTO_UPDATE_INSTALL()
    order_confirm = BotConfig.ORDER_CONFIRM_RESPONSE_ENABLED()
    review_response = BotConfig.REVIEW_RESPONSE_ENABLED()
    
    status_text = "⚙️ <b>Глобальные переключатели</b>\n\nЗдесь вы можете включать и отключать основные функции бота."
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_global_switches_menu(auto_bump, auto_delivery, auto_restore, auto_read, auto_ticket, auto_install, order_confirm, review_response)
    )


@router.callback_query(F.data == CBT.SWITCH_AUTO_RESTORE)
async def callback_switch_auto_restore(callback: CallbackQuery):
    """Переключить авто-восстановление"""
    # Переключаем
    current = BotConfig.AUTO_RESTORE_ENABLED()
    BotConfig.update(**{"auto_restore.enabled": not current})
    
    # Уведомление об изменении
    status = "включено" if not current else "выключено"
    await callback.answer(f"Авто-восстановление {status}", show_alert=False)
    
    # Обновляем меню
    auto_bump = BotConfig.AUTO_BUMP_ENABLED()
    auto_delivery = BotConfig.AUTO_DELIVERY_ENABLED()
    auto_restore = not current
    auto_read = BotConfig.AUTO_READ_ENABLED()
    auto_ticket = BotConfig.AUTO_TICKET_ENABLED()
    auto_install = BotConfig.AUTO_UPDATE_INSTALL()
    order_confirm = BotConfig.ORDER_CONFIRM_RESPONSE_ENABLED()
    review_response = BotConfig.REVIEW_RESPONSE_ENABLED()
    
    status_text = "⚙️ <b>Глобальные переключатели</b>\n\nЗдесь вы можете включать и отключать основные функции бота.\n\n"
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_global_switches_menu(auto_bump, auto_delivery, auto_restore, auto_read, auto_ticket, auto_install, order_confirm, review_response)
    )


@router.callback_query(F.data == CBT.SWITCH_AUTO_READ)
async def callback_switch_auto_read(callback: CallbackQuery):
    """Переключить авто-прочтение чатов"""
    # Переключаем
    current = BotConfig.AUTO_READ_ENABLED()
    BotConfig.update(**{"auto_read.enabled": not current})
    
    # Уведомление об изменении
    status = "включено" if not current else "выключено"
    await callback.answer(f"Авто-прочтение чатов {status}", show_alert=False)
    
    # Обновляем меню
    auto_bump = BotConfig.AUTO_BUMP_ENABLED()
    auto_delivery = BotConfig.AUTO_DELIVERY_ENABLED()
    auto_restore = BotConfig.AUTO_RESTORE_ENABLED()
    auto_read = not current
    auto_ticket = BotConfig.AUTO_TICKET_ENABLED()
    auto_install = BotConfig.AUTO_UPDATE_INSTALL()
    order_confirm = BotConfig.ORDER_CONFIRM_RESPONSE_ENABLED()
    review_response = BotConfig.REVIEW_RESPONSE_ENABLED()
    
    status_text = "⚙️ <b>Глобальные переключатели</b>\n\nЗдесь вы можете включать и отключать основные функции бота.\n\n"
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_global_switches_menu(auto_bump, auto_delivery, auto_restore, auto_read, auto_ticket, auto_install, order_confirm, review_response)
    )



@router.callback_query(F.data == CBT.SWITCH_USE_WATERMARK)
async def callback_switch_use_watermark(callback: CallbackQuery):
    """Переключить использование вотермарки в сообщениях"""
    current = BotConfig.USE_WATERMARK()
    BotConfig.update(**{"other.use_watermark": not current})

    status = "включено" if not current else "выключено"
    await callback.answer(f"Использование вотермарки {status}", show_alert=False)

    # Обновляем меню
    auto_bump = BotConfig.AUTO_BUMP_ENABLED()
    auto_delivery = BotConfig.AUTO_DELIVERY_ENABLED()
    auto_restore = BotConfig.AUTO_RESTORE_ENABLED()
    auto_read = BotConfig.AUTO_READ_ENABLED()
    auto_ticket = BotConfig.AUTO_TICKET_ENABLED()
    auto_install = BotConfig.AUTO_UPDATE_INSTALL()
    order_confirm = BotConfig.ORDER_CONFIRM_RESPONSE_ENABLED()
    review_response = BotConfig.REVIEW_RESPONSE_ENABLED()

    status_text = "⚙️ <b>Глобальные переключатели</b>\n\nЗдесь вы можете включать и отключать основные функции бота."

    await callback.message.edit_text(
        status_text,
        reply_markup=get_global_switches_menu(auto_bump, auto_delivery, auto_restore, auto_read, auto_ticket, auto_install, order_confirm, review_response)
    )


@router.callback_query(F.data == CBT.AUTO_TICKET_SETTINGS)
async def callback_auto_ticket_settings(callback: CallbackQuery):
    """Меню настроек авто-тикета"""
    enabled = BotConfig.AUTO_TICKET_ENABLED()
    interval = BotConfig.AUTO_TICKET_INTERVAL()
    max_orders = BotConfig.AUTO_TICKET_MAX_ORDERS()
    notify = BotConfig.NOTIFY_AUTO_TICKET()
    
    text = (
        "🎫 <b>Настройки авто-тикета</b>\n\n"
        "Бот будет автоматически создавать тикеты для неподтверждённых заказов.\n"
        "Для работы требуется, чтобы бот был авторизован.\n\n"
        f"Статус: <b>{'Включено ✅' if enabled else 'Выключено ❌'}</b>"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_auto_ticket_settings_menu(enabled, interval, max_orders, notify)
    )

@router.callback_query(F.data == CBT.SWITCH_AUTO_TICKET_INTERNAL)
async def callback_switch_auto_ticket_internal(callback: CallbackQuery):
    """Переключить авто-тикет (внутри настроек)"""
    # Переключаем
    current = BotConfig.AUTO_TICKET_ENABLED()
    BotConfig.update(**{"auto_ticket.enabled": not current})
    
    # Уведомление об изменении
    status = "включен" if not current else "выключен"
    await callback.answer(f"Авто-тикет {status}", show_alert=False)
    
    # Обновляем меню настроек (остаемся в нем)
    enabled = not current
    interval = BotConfig.AUTO_TICKET_INTERVAL()
    max_orders = BotConfig.AUTO_TICKET_MAX_ORDERS()
    notify = BotConfig.NOTIFY_AUTO_TICKET()
    
    text = (
        "🎫 <b>Настройки авто-тикета</b>\n\n"
        "Бот будет автоматически создавать тикеты для неподтверждённых заказов.\n"
        "Для работы требуется, чтобы бот был авторизован.\n\n"
        f"Статус: <b>{'Включено ✅' if enabled else 'Выключено ❌'}</b>"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_auto_ticket_settings_menu(enabled, interval, max_orders, notify)
    )


@router.callback_query(F.data == CBT.SWITCH_AUTO_TICKET)
async def callback_switch_auto_ticket(callback: CallbackQuery):
    """Переключить авто-тикет (глобальное меню)"""
    # Переключаем
    current = BotConfig.AUTO_TICKET_ENABLED()
    BotConfig.update(**{"auto_ticket.enabled": not current})
    
    # Уведомление об изменении
    status = "включен" if not current else "выключен"
    await callback.answer(f"Авто-тикет {status}", show_alert=False)
    
    # Обновляем глобальное меню
    auto_bump = BotConfig.AUTO_BUMP_ENABLED()
    auto_delivery = BotConfig.AUTO_DELIVERY_ENABLED()
    auto_restore = BotConfig.AUTO_RESTORE_ENABLED()
    auto_read = BotConfig.AUTO_READ_ENABLED()
    auto_ticket = not current
    auto_install = BotConfig.AUTO_UPDATE_INSTALL()
    order_confirm = BotConfig.ORDER_CONFIRM_RESPONSE_ENABLED()
    review_response = BotConfig.REVIEW_RESPONSE_ENABLED()
    
    status_text = "⚙️ <b>Глобальные переключатели</b>\n\nЗдесь вы можете включать и отключать основные функции бота.\n\n"
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_global_switches_menu(auto_bump, auto_delivery, auto_restore, auto_read, auto_ticket, auto_install, order_confirm, review_response)
    )


@router.callback_query(F.data == CBT.SWITCH_AUTO_TICKET_NOTIFY)
async def callback_switch_auto_ticket_notify(callback: CallbackQuery):
    """Переключить уведомления авто-тикета"""
    current = BotConfig.NOTIFY_AUTO_TICKET()
    BotConfig.update(**{"notifications.auto_ticket": not current})
    
    await callback.answer(f"Уведомления {'включены' if not current else 'выключены'}", show_alert=False)
    
    # Обновляем меню
    enabled = BotConfig.AUTO_TICKET_ENABLED()
    interval = BotConfig.AUTO_TICKET_INTERVAL()
    max_orders = BotConfig.AUTO_TICKET_MAX_ORDERS()
    notify = not current
    
    text = (
        "🎫 <b>Настройки авто-тикета</b>\n\n"
        "Бот будет автоматически создавать тикеты для неподтверждённых заказов.\n"
        "Для работы требуется, чтобы бот был авторизован.\n\n"
        f"Статус: <b>{'Включено ✅' if enabled else 'Выключено ❌'}</b>"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_auto_ticket_settings_menu(enabled, interval, max_orders, notify)
    )


@router.callback_query(F.data == CBT.AUTO_TICKET_SET_INTERVAL)
async def callback_auto_ticket_set_interval(callback: CallbackQuery, state: FSMContext):
    """Запросить интервал проверки вручную"""
    await state.set_state(AutoTicketState.waiting_for_interval)
    await callback.message.answer(
        "⏱️ Введите интервал проверки в минутах (30-1440):\n\n"
        "Например: <code>60</code> (1 час)\n"
        "Отправьте /cancel для отмены",
    )
    await callback.answer()


@router.message(AutoTicketState.waiting_for_interval)
async def process_auto_ticket_interval(message: Message, state: FSMContext):
    """Обработать ввод интервала"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено")
        return
    
    try:
        interval_minutes = int(message.text.strip())
        
        if interval_minutes < 30 or interval_minutes > 1440:
            await message.answer(
                "❌ Интервал должен быть от 30 до 1440 минут (24 часа)\n"
                "Попробуйте ещё раз или отправьте /cancel"
            )
            return
        
        interval_seconds = interval_minutes * 60
        BotConfig.update(**{"auto_ticket.interval": interval_seconds})
        await state.clear()
        
        await message.answer(
            f"✅ Интервал установлен: {interval_minutes} мин ({interval_seconds} сек)"
        )
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите число от 30 до 1440\n"
            "Отправьте /cancel для отмены"
        )


@router.callback_query(F.data == CBT.AUTO_TICKET_SET_MAX)
async def callback_auto_ticket_set_max(callback: CallbackQuery, state: FSMContext):
    """Запросить макс. заказов вручную"""
    await state.set_state(AutoTicketState.waiting_for_max_orders)
    await callback.message.answer(
        "🔢 Введите максимальное количество заказов для обработки за раз (1-50):\n\n"
        "Например: <code>5</code>\n"
        "Отправьте /cancel для отмены",
    )
    await callback.answer()


@router.message(AutoTicketState.waiting_for_max_orders)
async def process_auto_ticket_max_orders(message: Message, state: FSMContext):
    """Обработать ввод макс. заказов"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено")
        return
    
    try:
        max_orders = int(message.text.strip())
        
        if max_orders < 1 or max_orders > 50:
            await message.answer(
                "❌ Количество должно быть от 1 до 50\n"
                "Попробуйте ещё раз или отправьте /cancel"
            )
            return
        
        BotConfig.update(**{"auto_ticket.max_orders": max_orders})
        await state.clear()
        
        await message.answer(f"✅ Макс. заказов установлено: {max_orders}")
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите число от 1 до 50\n"
            "Отправьте /cancel для отмены"
        )


def _proxy_menu_text() -> str:
    """Текст меню прокси с текущим состоянием."""
    enabled = BotConfig.PROXY_ENABLED()
    ptype = BotConfig.PROXY_TYPE()
    ip = BotConfig.PROXY_IP()
    port = BotConfig.PROXY_PORT()
    has_auth = bool(BotConfig.PROXY_LOGIN())
    addr = f"{ip}:{port}" if (ip and port) else "не задан"
    return (
        "🌐 <b>Прокси для Telegram</b>\n\n"
        "Позволяет боту подключаться к Telegram через прокси — полезно, если "
        "Telegram заблокирован у провайдера (напр. в РФ).\n\n"
        "Поддерживаются типы прокси:\n"
        "• SOCKS5 (рекомендуется)\n"
        "• SOCKS4\n"
        "• HTTP / HTTPS\n\n"
        "Настроить прокси можно:\n"
        "• В мастере установки (Setup)\n"
        "• В этом меню — все настройки через инлайн-кнопки\n\n"
        f"<b>Статус:</b> {'✅ Включён' if enabled else '❌ Выключен'}\n"
        f"<b>Тип:</b> {ptype}\n"
        f"<b>Адрес:</b> {addr}\n"
        f"<b>Авторизация:</b> {'задана' if has_auth else 'нет'}\n\n"
        "⚠️ После изменения прокси перезапустите бота (/restart), "
        "чтобы прокси применился к подключению Telegram."
    )


def _proxy_menu_kb():
    return get_proxy_menu(
        BotConfig.PROXY_ENABLED(),
        BotConfig.PROXY_TYPE(),
        BotConfig.PROXY_IP(),
        BotConfig.PROXY_PORT(),
        bool(BotConfig.PROXY_LOGIN()),
    )


@router.callback_query(F.data == CBT.PROXY_MENU)
async def callback_proxy_menu(callback: CallbackQuery):
    """Меню настроек прокси."""
    await callback.message.edit_text(_proxy_menu_text(), reply_markup=_proxy_menu_kb())
    await callback.answer()


@router.callback_query(F.data == CBT.SWITCH_PROXY)
async def callback_switch_proxy(callback: CallbackQuery):
    """Включить/выключить прокси."""
    current = BotConfig.PROXY_ENABLED()
    if not current and (not BotConfig.PROXY_IP() or not BotConfig.PROXY_PORT()):
        await callback.answer("Сначала задайте адрес прокси (IP:порт)", show_alert=True)
        return
    get_config_manager().set('Proxy', 'enabled', not current)
    await callback.answer(
        f"Прокси {'включён' if not current else 'выключен'}. Перезапустите бота (/restart).",
        show_alert=False,
    )
    await callback.message.edit_text(_proxy_menu_text(), reply_markup=_proxy_menu_kb())


@router.callback_query(F.data == CBT.PROXY_SET_TYPE)
async def callback_proxy_set_type(callback: CallbackQuery):
    """Циклически переключить тип прокси."""
    order = ['socks5', 'socks4', 'http', 'https']
    cur = BotConfig.PROXY_TYPE()
    try:
        nxt = order[(order.index(cur) + 1) % len(order)]
    except ValueError:
        nxt = 'socks5'
    get_config_manager().set('Proxy', 'type', nxt)
    await callback.answer(f"Тип прокси: {nxt}", show_alert=False)
    await callback.message.edit_text(_proxy_menu_text(), reply_markup=_proxy_menu_kb())


@router.callback_query(F.data == CBT.PROXY_SET_ADDR)
async def callback_proxy_set_addr(callback: CallbackQuery, state: FSMContext):
    """Запросить адрес прокси."""
    await state.set_state(ProxyState.waiting_for_addr)
    await callback.message.answer(
        "🌐 Введите адрес прокси в формате <code>IP:порт</code>\n\n"
        "Например: <code>127.0.0.1:1080</code>\n"
        "Можно сразу с логином/паролем: <code>IP:порт:логин:пароль</code>\n\n"
        "Отправьте /cancel для отмены"
    )
    await callback.answer()


@router.message(ProxyState.waiting_for_addr)
async def process_proxy_addr(message: Message, state: FSMContext):
    """Обработать ввод адреса прокси."""
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено")
        return

    raw = (message.text or "").strip()
    parts = raw.split(":")
    if len(parts) < 2:
        await message.answer(
            "❌ Неверный формат. Нужно минимум <code>IP:порт</code>\n"
            "Отправьте /cancel для отмены"
        )
        return

    ip = parts[0].strip()
    port = parts[1].strip()
    if not ip or not port.isdigit() or not (0 < int(port) < 65536):
        await message.answer(
            "❌ Порт должен быть числом 1-65535, адрес — не пустым.\n"
            "Отправьте /cancel для отмены"
        )
        return

    cm = get_config_manager()
    cm.set('Proxy', 'ip', ip)
    cm.set('Proxy', 'port', port)

    auth_msg = ""
    if len(parts) >= 4:
        cm.set('Proxy', 'login', parts[2].strip())
        cm.set('Proxy', 'password', parts[3].strip())
        auth_msg = " + логин/пароль"

    await state.clear()
    await message.answer(
        f"✅ Адрес прокси сохранён: <code>{ip}:{port}</code>{auth_msg}\n\n"
        "Включите прокси в меню и перезапустите бота (/restart)."
    )


@router.callback_query(F.data == CBT.PROXY_SET_AUTH)
async def callback_proxy_set_auth(callback: CallbackQuery, state: FSMContext):
    """Запросить логин/пароль прокси."""
    await state.set_state(ProxyState.waiting_for_auth)
    await callback.message.answer(
        "🔑 Введите логин и пароль прокси в формате <code>логин:пароль</code>\n\n"
        "Если пароля нет — просто <code>логин</code>\n"
        "Отправьте /cancel для отмены"
    )
    await callback.answer()


@router.message(ProxyState.waiting_for_auth)
async def process_proxy_auth(message: Message, state: FSMContext):
    """Обработать ввод логина/пароля прокси."""
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено")
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer("❌ Пусто. Отправьте логин:пароль или /cancel")
        return

    login, _, password = raw.partition(":")
    cm = get_config_manager()
    cm.set('Proxy', 'login', login.strip())
    cm.set('Proxy', 'password', password.strip())
    await state.clear()
    await message.answer(
        "✅ Авторизация прокси сохранена.\n"
        "Перезапустите бота (/restart), чтобы применить."
    )


@router.callback_query(F.data == CBT.PROXY_CLEAR_AUTH)
async def callback_proxy_clear_auth(callback: CallbackQuery):
    """Очистить логин/пароль прокси."""
    cm = get_config_manager()
    cm.set('Proxy', 'login', '')
    cm.set('Proxy', 'password', '')
    await callback.answer("Логин/пароль очищены", show_alert=False)
    await callback.message.edit_text(_proxy_menu_text(), reply_markup=_proxy_menu_kb())


@router.callback_query(F.data == CBT.SWITCH_AUTO_INSTALL)
async def callback_switch_auto_install(callback: CallbackQuery):
    """Переключить автоматическую установку обновлений"""
    # Переключаем
    current = BotConfig.AUTO_UPDATE_INSTALL()
    BotConfig.update(**{"AutoUpdate.auto_install": not current})
    
    # Уведомление об изменении
    status = "включена" if not current else "выключена"
    await callback.answer(f"Авто-установка обновлений {status}", show_alert=False)
    
    # Обновляем меню
    auto_bump = BotConfig.AUTO_BUMP_ENABLED()
    auto_delivery = BotConfig.AUTO_DELIVERY_ENABLED()
    auto_restore = BotConfig.AUTO_RESTORE_ENABLED()
    auto_read = BotConfig.AUTO_READ_ENABLED()
    auto_ticket = BotConfig.AUTO_TICKET_ENABLED()
    auto_install = not current
    order_confirm = BotConfig.ORDER_CONFIRM_RESPONSE_ENABLED()
    review_response = BotConfig.REVIEW_RESPONSE_ENABLED()
    
    status_text = "⚙️ <b>Глобальные переключатели</b>\n\nЗдесь вы можете включать и отключать основные функции бота.\n\n"
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_global_switches_menu(auto_bump, auto_delivery, auto_restore, auto_read, auto_ticket, auto_install, order_confirm, review_response)
    )


@router.callback_query(F.data == CBT.SWITCH_ORDER_CONFIRM)
async def callback_switch_order_confirm(callback: CallbackQuery, auto_response, **kwargs):
    """Переключить авто-ответ на подтверждение заказа"""
    # Переключаем
    current = BotConfig.ORDER_CONFIRM_RESPONSE_ENABLED()
    new_state = not current
    BotConfig.update(**{"AutoResponse.orderConfirm": new_state})
    
    # Если включаем функцию - инициализируем существующие заказы
    if new_state:
        await auto_response._initialize_processed_orders()
    
    # Уведомление об изменении
    status = "включен" if new_state else "выключен"
    await callback.answer(f"Авто-ответ на подтверждение заказа {status}", show_alert=False)
    
    # Обновляем меню - возвращаемся в меню настройки ответа
    from bot.keyboards import get_order_confirm_response_menu
    enabled = new_state
    text = BotConfig.ORDER_CONFIRM_RESPONSE_TEXT()
    
    message_text = (
        "✅ <b>Ответ на подтверждение заказа</b>\n\n"
        f"<b>Статус:</b> {'включено ✅' if enabled else 'выключено ❌'}\n\n"
        f"<b>Текущий текст ответа:</b>\n<i>{text}</i>\n\n"
        "При завершении заказа бот автоматически отправит это сообщение покупателю."
    )
    
    await callback.message.edit_text(
        message_text,
        reply_markup=get_order_confirm_response_menu(enabled, text)
    )


@router.callback_query(F.data == CBT.SWITCH_REVIEW_RESPONSE)
async def callback_switch_review_response(callback: CallbackQuery, auto_response, **kwargs):
    """Переключить авто-ответ на отзыв"""
    # Переключаем
    current = BotConfig.REVIEW_RESPONSE_ENABLED()
    new_state = not current
    BotConfig.update(**{"AutoResponse.reviewResponse": new_state})
    
    # Если включаем функцию - инициализируем существующие заказы
    if new_state:
        await auto_response._initialize_processed_orders()
    
    # Уведомление об изменении
    status = "включен" if new_state else "выключен"
    await callback.answer(f"Авто-ответ на отзыв {status}", show_alert=False)
    
    # Обновляем меню - возвращаемся в меню настройки ответа
    from bot.keyboards import get_review_response_menu
    enabled = new_state
    text = BotConfig.REVIEW_RESPONSE_TEXT()
    
    message_text = (
        "⭐ <b>Ответ на отзыв</b>\n\n"
        f"<b>Статус:</b> {'включено ✅' if enabled else 'выключено ❌'}\n\n"
        f"<b>Текущий текст ответа:</b>\n<i>{text}</i>\n\n"
        "При получении отзыва бот автоматически отправит это сообщение."
    )
    
    await callback.message.edit_text(
        message_text,
        reply_markup=get_review_response_menu(enabled, text)
    )


@router.callback_query(F.data == "empty")
async def callback_empty(callback: CallbackQuery):
    """Пустой callback (для неактивных кнопок)"""
    await callback.answer()


@router.callback_query(F.data == CBT.AUTO_DELIVERY)
async def callback_auto_delivery_menu(callback: CallbackQuery, auto_delivery, **kwargs):
    """Меню автовыдачи"""
    await callback.answer()
    
    lots = await auto_delivery.get_lots()
    
    keyboard = get_auto_delivery_lots_menu(lots, offset=0)
    
    text = "📦 <b>Лоты с автовыдачей</b>\n\n"
    text += f"Всего лотов: <code>{len(lots)}</code>"
    
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == CBT.BLACKLIST)
async def callback_blacklist_menu(callback: CallbackQuery, **kwargs):
    """Меню чёрного списка"""
    await callback.answer()
    
    # Получаем список из конфига
    blacklist = []
    config = get_config_manager()
    if config._config.has_section("Blacklist"):
        sections = [s for s in config._config.sections() if s.startswith("Blacklist.")]
        
        for section in sections:
            username = section.replace("Blacklist.", "", 1)
            block_delivery = BotConfig.get(f"{section}.block_delivery", True, bool)
            block_response = BotConfig.get(f"{section}.block_response", True, bool)
            
            blacklist.append({
                "username": username,
                "block_delivery": block_delivery,
                "block_response": block_response
            })
    
    keyboard = get_blacklist_menu(blacklist, offset=0)
    
    text = "🚫 <b>Чёрный список</b>\n\n"
    text += f"Заблокировано пользователей: <code>{len(blacklist)}</code>"
    
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == CBT.PLUGINS)
async def callback_plugins_menu(callback: CallbackQuery, plugin_manager, **kwargs):
    """Меню плагинов"""
    await callback.answer()
    
    # Получаем плагины
    plugins_data = []
    for uuid, plugin in plugin_manager.plugins.items():
        plugins_data.append({
            "uuid": uuid,
            "name": plugin.name,
            "version": plugin.version,
            "description": plugin.description,
            "enabled": plugin.enabled
        })
    
    keyboard = get_plugins_menu(plugins_data, offset=0)
    
    enabled_count = sum(1 for p in plugins_data if p["enabled"])
    disabled_count = len(plugins_data) - enabled_count
    
    text = "🧩 <b>Управление плагинами</b>\n\n"
    text += f"🧩 Всего плагинов: <code>{len(plugins_data)}</code>\n"
    text += f"✅ Активных: <code>{enabled_count}</code>\n"
    text += f"❌ Отключенных: <code>{disabled_count}</code>\n\n"
    text += "⚠️ После активации/деактивации/удаления плагина необходимо перезапустить бота! /restart"
    
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == CBT.ABOUT)
async def callback_about(callback: CallbackQuery):
    """Показать информацию о боте и ссылки автора"""
    await callback.answer()

    text = (
        "ℹ️ <b>О боте</b>\n\n"
        "Starvell Cardinal — автоматизационный бот для Starvell.com.\n\n"
        "Автор: @embedium\n"
        "Telegram: @embedium\n"
        "Канал с новостями: @StarvellCardinal\n"
        "Канал с плагинами: @StarvellPlugins\n"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Telegram", url="https://t.me/embedium")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=CBT.MAIN)]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == CBT.NOTIFICATIONS)
async def callback_notifications(callback: CallbackQuery):
    """Меню настроек уведомлений"""
    await callback.answer()
    
    # Загружаем текущий язык
    
    
    # Получаем текущие настройки
    messages = BotConfig.NOTIFY_NEW_MESSAGES()
    orders = BotConfig.NOTIFY_NEW_ORDERS()
    support_messages = BotConfig.NOTIFY_SUPPORT_MESSAGES()
    restore = BotConfig.NOTIFY_LOT_RESTORE()
    start = BotConfig.NOTIFY_BOT_START()
    stop = BotConfig.NOTIFY_BOT_STOP()
    auto_ticket = BotConfig.NOTIFY_AUTO_TICKET()
    order_confirm = BotConfig.NOTIFY_ORDER_CONFIRMED()
    review = BotConfig.NOTIFY_REVIEW()
    auto_responses = BotConfig.NOTIFY_AUTO_RESPONSES()
    
    # Формируем описание
    status_text = "🔔 <b>Настройки уведомлений</b>\n\nНастройте какие уведомления, которые вам нужны получать."
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, support_messages)
    )


@router.callback_query(F.data == CBT.NOTIF_MESSAGES)
async def callback_notif_messages(callback: CallbackQuery):
    """Переключить уведомления о новых сообщениях"""
    current = BotConfig.NOTIFY_NEW_MESSAGES()
    BotConfig.update(**{"notifications.new_messages": not current})
    
    
    status = "включены" if not current else "выключены"
    await callback.answer(f"Уведомления о сообщениях {status}", show_alert=False)
    
    # Обновляем меню
    messages = not current
    orders = BotConfig.NOTIFY_NEW_ORDERS()
    support_messages = BotConfig.NOTIFY_SUPPORT_MESSAGES()
    restore = BotConfig.NOTIFY_LOT_RESTORE()
    start = BotConfig.NOTIFY_BOT_START()
    stop = BotConfig.NOTIFY_BOT_STOP()
    auto_ticket = BotConfig.NOTIFY_AUTO_TICKET()
    order_confirm = BotConfig.NOTIFY_ORDER_CONFIRMED()
    review = BotConfig.NOTIFY_REVIEW()
    auto_responses = BotConfig.NOTIFY_AUTO_RESPONSES()
    
    status_text = "🔔 <b>Настройки уведомлений</b>\n\nНастройте какие уведомления, которые вам нужны получать."
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, support_messages)
    )


@router.callback_query(F.data == CBT.NOTIF_ORDERS)
async def callback_notif_orders(callback: CallbackQuery):
    """Переключить уведомления о новых заказах"""
    current = BotConfig.NOTIFY_NEW_ORDERS()
    BotConfig.update(**{"notifications.new_orders": not current})
    
    
    status = "включены" if not current else "выключены"
    await callback.answer(f"Уведомления о заказах {status}", show_alert=False)
    
    # Обновляем меню
    messages = BotConfig.NOTIFY_NEW_MESSAGES()
    orders = not current
    support_messages = BotConfig.NOTIFY_SUPPORT_MESSAGES()
    restore = BotConfig.NOTIFY_LOT_RESTORE()
    start = BotConfig.NOTIFY_BOT_START()
    stop = BotConfig.NOTIFY_BOT_STOP()
    auto_ticket = BotConfig.NOTIFY_AUTO_TICKET()
    order_confirm = BotConfig.NOTIFY_ORDER_CONFIRMED()
    review = BotConfig.NOTIFY_REVIEW()
    auto_responses = BotConfig.NOTIFY_AUTO_RESPONSES()
    
    status_text = "🔔 <b>Настройки уведомлений</b>\n\nНастройте какие уведомления, которые вам нужны получать."
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, support_messages)
    )


@router.callback_query(F.data == CBT.NOTIF_SUPPORT_MESSAGES)
async def callback_notif_support_messages(callback: CallbackQuery):
    """Переключить уведомления о сообщениях от поддержки"""
    current = BotConfig.NOTIFY_SUPPORT_MESSAGES()
    BotConfig.update(**{"notifications.support_messages": not current})
    
    
    status = "включены" if not current else "выключены"
    await callback.answer(f"Уведомления от поддержки {status}", show_alert=False)
    
    # Обновляем меню
    messages = BotConfig.NOTIFY_NEW_MESSAGES()
    orders = BotConfig.NOTIFY_NEW_ORDERS()
    support_messages = not current
    restore = BotConfig.NOTIFY_LOT_RESTORE()
    start = BotConfig.NOTIFY_BOT_START()
    stop = BotConfig.NOTIFY_BOT_STOP()
    auto_ticket = BotConfig.NOTIFY_AUTO_TICKET()
    order_confirm = BotConfig.NOTIFY_ORDER_CONFIRMED()
    review = BotConfig.NOTIFY_REVIEW()
    auto_responses = BotConfig.NOTIFY_AUTO_RESPONSES()
    
    status_text = "🔔 <b>Настройки уведомлений</b>\n\nНастройте какие уведомления, которые вам нужны получать."
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, support_messages)
    )


@router.callback_query(F.data == CBT.NOTIF_RESTORE)
async def callback_notif_restore(callback: CallbackQuery):
    """Переключить уведомления о восстановлении лота"""
    current = BotConfig.NOTIFY_LOT_RESTORE()
    BotConfig.update(**{"notifications.lot_restore": not current})
    
    
    status = "включены" if not current else "выключены"
    await callback.answer(f"Уведомления о восстановлении {status}", show_alert=False)
    
    # Обновляем меню
    messages = BotConfig.NOTIFY_NEW_MESSAGES()
    orders = BotConfig.NOTIFY_NEW_ORDERS()
    restore = not current
    start = BotConfig.NOTIFY_BOT_START()
    stop = BotConfig.NOTIFY_BOT_STOP()
    auto_ticket = BotConfig.NOTIFY_AUTO_TICKET()
    order_confirm = BotConfig.NOTIFY_ORDER_CONFIRMED()
    review = BotConfig.NOTIFY_REVIEW()
    auto_responses = BotConfig.NOTIFY_AUTO_RESPONSES()
    
    status_text = "🔔 <b>Настройки уведомлений</b>\n\nНастройте какие уведомления, которые вам нужны получать."
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, BotConfig.NOTIFY_SUPPORT_MESSAGES())
    )


@router.callback_query(F.data == CBT.NOTIF_START)
async def callback_notif_start(callback: CallbackQuery):
    """Переключить уведомления о запуске бота"""
    current = BotConfig.NOTIFY_BOT_START()
    BotConfig.update(**{"notifications.bot_start": not current})
    
    
    status = "включены" if not current else "выключены"
    await callback.answer(f"Уведомления о запуске {status}", show_alert=False)
    
    # Обновляем меню
    messages = BotConfig.NOTIFY_NEW_MESSAGES()
    orders = BotConfig.NOTIFY_NEW_ORDERS()
    restore = BotConfig.NOTIFY_LOT_RESTORE()
    start = not current
    stop = BotConfig.NOTIFY_BOT_STOP()
    auto_ticket = BotConfig.NOTIFY_AUTO_TICKET()
    order_confirm = BotConfig.NOTIFY_ORDER_CONFIRMED()
    review = BotConfig.NOTIFY_REVIEW()
    auto_responses = BotConfig.NOTIFY_AUTO_RESPONSES()
    
    status_text = "🔔 <b>Настройки уведомлений</b>\n\nНастройте какие уведомления, которые вам нужны получать."
    
    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, BotConfig.NOTIFY_SUPPORT_MESSAGES())
    )



@router.callback_query(F.data == CBT.NOTIF_AUTO_RESPONSES)
async def callback_notif_auto_responses(callback: CallbackQuery):
    """Переключить уведомления при выполнении автоответов/команд"""
    current = BotConfig.NOTIFY_AUTO_RESPONSES()
    BotConfig.update(**{"notifications.auto_responses": not current})

    status = "включены" if not current else "выключены"
    await callback.answer(f"Уведомления автоответов {status}", show_alert=False)

    # Обновляем меню
    messages = BotConfig.NOTIFY_NEW_MESSAGES()
    orders = BotConfig.NOTIFY_NEW_ORDERS()
    restore = BotConfig.NOTIFY_LOT_RESTORE()
    start = BotConfig.NOTIFY_BOT_START()
    stop = BotConfig.NOTIFY_BOT_STOP()
    auto_ticket = BotConfig.NOTIFY_AUTO_TICKET()
    order_confirm = BotConfig.NOTIFY_ORDER_CONFIRMED()
    review = BotConfig.NOTIFY_REVIEW()
    auto_responses = not current

    status_text = "🔔 <b>Настройки уведомлений</b>\\n\\nНастройте какие уведомления, которые вам нужны получать."

    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, BotConfig.NOTIFY_SUPPORT_MESSAGES())
    )


@router.callback_query(F.data == CBT.NOTIF_ORDER_CONFIRMED)
async def callback_notif_order_confirmed(callback: CallbackQuery):
    """Переключить уведомления о подтверждении заказа"""
    current = BotConfig.NOTIFY_ORDER_CONFIRMED()
    BotConfig.update(**{"notifications.order_confirmed": not current})

    status = "включены" if not current else "выключены"
    await callback.answer(f"Уведомления о подтверждении заказа {status}", show_alert=False)

    # Обновляем меню
    messages = BotConfig.NOTIFY_NEW_MESSAGES()
    orders = BotConfig.NOTIFY_NEW_ORDERS()
    restore = BotConfig.NOTIFY_LOT_RESTORE()
    start = BotConfig.NOTIFY_BOT_START()
    stop = BotConfig.NOTIFY_BOT_STOP()
    auto_ticket = BotConfig.NOTIFY_AUTO_TICKET()
    order_confirm = not current
    review = BotConfig.NOTIFY_REVIEW()
    auto_responses = BotConfig.NOTIFY_AUTO_RESPONSES()

    status_text = "🔔 <b>Настройки уведомлений</b>\\n\\nНастройте какие уведомления, которые вам нужны получать."

    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, BotConfig.NOTIFY_SUPPORT_MESSAGES())
    )


@router.callback_query(F.data == CBT.NOTIF_AUTO_TICKET)
async def callback_notif_auto_ticket(callback: CallbackQuery):
    """Переключить уведомления об отправке авто-тикета"""
    current = BotConfig.NOTIFY_AUTO_TICKET()
    BotConfig.update(**{"notifications.auto_ticket": not current})

    status = "включены" if not current else "выключены"
    await callback.answer(f"Уведомления авто-тикета {status}", show_alert=False)

    # Обновляем меню
    messages = BotConfig.NOTIFY_NEW_MESSAGES()
    orders = BotConfig.NOTIFY_NEW_ORDERS()
    restore = BotConfig.NOTIFY_LOT_RESTORE()
    start = BotConfig.NOTIFY_BOT_START()
    stop = BotConfig.NOTIFY_BOT_STOP()
    auto_ticket = not current
    order_confirm = BotConfig.NOTIFY_ORDER_CONFIRMED()
    review = BotConfig.NOTIFY_REVIEW()
    auto_responses = BotConfig.NOTIFY_AUTO_RESPONSES()

    status_text = "🔔 <b>Настройки уведомлений</b>\\n\\nНастройте какие уведомления, которые вам нужны получать."

    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, BotConfig.NOTIFY_SUPPORT_MESSAGES())
    )


@router.callback_query(F.data == CBT.NOTIF_STOP)
async def callback_notif_stop(callback: CallbackQuery):
    """Переключить уведомления об остановке бота"""
    current = BotConfig.NOTIFY_BOT_STOP()
    BotConfig.update(**{"notifications.bot_stop": not current})

    status = "включены" if not current else "выключены"
    await callback.answer(f"Уведомления об остановке бота {status}", show_alert=False)

    # Обновляем меню
    messages = BotConfig.NOTIFY_NEW_MESSAGES()
    orders = BotConfig.NOTIFY_NEW_ORDERS()
    restore = BotConfig.NOTIFY_LOT_RESTORE()
    start = BotConfig.NOTIFY_BOT_START()
    stop = not current
    auto_ticket = BotConfig.NOTIFY_AUTO_TICKET()
    order_confirm = BotConfig.NOTIFY_ORDER_CONFIRMED()
    review = BotConfig.NOTIFY_REVIEW()
    auto_responses = BotConfig.NOTIFY_AUTO_RESPONSES()

    status_text = "🔔 <b>Настройки уведомлений</b>\\n\\nНастройте какие уведомления, которые вам нужны получать."

    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, BotConfig.NOTIFY_SUPPORT_MESSAGES())
    )


@router.callback_query(F.data == CBT.NOTIF_REVIEW)
async def callback_notif_review(callback: CallbackQuery):
    """Переключить уведомления о новых отзывах"""
    current = BotConfig.NOTIFY_REVIEW()
    BotConfig.update(**{"notifications.review": not current})

    status = "включены" if not current else "выключены"
    await callback.answer(f"Уведомления о новых отзывах {status}", show_alert=False)

    # Обновляем меню
    messages = BotConfig.NOTIFY_NEW_MESSAGES()
    orders = BotConfig.NOTIFY_NEW_ORDERS()
    restore = BotConfig.NOTIFY_LOT_RESTORE()
    start = BotConfig.NOTIFY_BOT_START()
    stop = BotConfig.NOTIFY_BOT_STOP()
    auto_ticket = BotConfig.NOTIFY_AUTO_TICKET()
    order_confirm = BotConfig.NOTIFY_ORDER_CONFIRMED()
    review = not current
    auto_responses = BotConfig.NOTIFY_AUTO_RESPONSES()

    status_text = "🔔 <b>Настройки уведомлений</b>\\n\\nНастройте какие уведомления, которые вам нужны получать."

    await callback.message.edit_text(
        status_text,
        reply_markup=get_notifications_menu(messages, orders, restore, start, stop, auto_ticket, order_confirm, review, auto_responses, BotConfig.NOTIFY_SUPPORT_MESSAGES())
    )





# === Обработчик кнопки "Ответить" из уведомлений ===

@router.callback_query(F.data.startswith("r:"))
async def handle_reply_button(callback: CallbackQuery, state: FSMContext, **kwargs):
    """Обработка нажатия кнопки 'Ответить' в уведомлении"""
    # Извлекаем chat_id из callback data (формат: r:chat_id)
    chat_id = callback.data.split(":", 1)[1]
    
    # Сохраняем chat_id в состояние
    await state.update_data(reply_chat_id=chat_id)
    await state.set_state(ReplyState.waiting_for_reply)
    
    await callback.answer()
    await callback.message.answer(
        "✍️ <b>Быстрый ответ</b>\n\n"
        "Отправьте сообщение, которое хотите отправить пользователю.\n\n"
        "Для отмены используйте /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="reply_cancel")]
        ])
    )


@router.callback_query(F.data == "reply_cancel")
async def handle_reply_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена быстрого ответа"""
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.delete()


@router.message(ReplyState.waiting_for_reply)
async def process_quick_reply(message: Message, state: FSMContext, **kwargs):
    """Обработка отправки быстрого ответа"""
    # Получаем starvell из kwargs
    starvell = kwargs.get('starvell')
    
    if not starvell:
        await message.answer("❌ Ошибка: сервис Starvell недоступен")
        await state.clear()
        return
    
    # Получаем сохраненный chat_id
    data = await state.get_data()
    chat_id = data.get("reply_chat_id")
    
    if not chat_id:
        await message.answer("❌ Ошибка: не удалось определить чат")
        await state.clear()
        return
    
    # Отправляем сообщение
    try:
        status_msg = await message.answer("📤 Отправка сообщения...")
        
        result = await starvell.send_message(chat_id, message.text)
        
        await status_msg.edit_text(
            "✅ <b>Сообщение отправлено!</b>\n\n"
            f"💬 Текст: <code>{message.text[:100]}</code>"
        )
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке: {e}")
        await state.clear()


# === Обработчик кнопки "Вернуть деньги" ===

@router.callback_query(F.data.startswith("refund:"))
async def handle_refund_button(callback: CallbackQuery):
    """Обработка нажатия кнопки 'Вернуть деньги' - запрос подтверждения"""
    # Извлекаем короткий ID заказа
    short_order_id = callback.data.split(":", 1)[1]
    
    # Создаем кнопки подтверждения
    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, вернуть",
                callback_data=f"refund_confirm:{short_order_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="refund_cancel"
            )
        ]
    ])
    
    await callback.message.edit_reply_markup(reply_markup=confirm_keyboard)
    await callback.answer("⚠️ Подтвердите возврат денег", show_alert=True)


@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirm_order(callback: CallbackQuery, **kwargs):
    """Обработка подтверждения заказа"""
    short_order_id = callback.data.split(":", 1)[1]
    
    # Получаем starvell из kwargs
    starvell = kwargs.get('starvell')
    
    if not starvell:
        await callback.answer("❌ Ошибка: сервис Starvell недоступен", show_alert=True)
        return
    
    try:
        # Подтверждаем заказ
        await callback.answer("⏳ Подтверждение заказа...", show_alert=False)
        
        result = await starvell.confirm_order(short_order_id)
        
        # Обновляем сообщение
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>Заказ подтверждён!</b>",
            reply_markup=None
        )
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка при подтверждении: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("refund_confirm:"))
async def handle_refund_confirm(callback: CallbackQuery, **kwargs):
    """Подтверждение возврата денег"""
    short_order_id = callback.data.split(":", 1)[1]
    
    # Получаем starvell из kwargs
    starvell = kwargs.get('starvell')
    
    if not starvell:
        await callback.answer("❌ Ошибка: сервис Starvell недоступен", show_alert=True)
        return
    
    try:
        # Выполняем возврат
        await callback.answer("⏳ Выполняется возврат...", show_alert=False)
        
        result = await starvell.refund_order(short_order_id)
        
        # Обновляем сообщение
        await callback.message.edit_text(
            callback.message.text + "\n\n💰 <b>Деньги возвращены!</b>",
            reply_markup=None
        )
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка при возврате: {str(e)}", show_alert=True)
        # Восстанавливаем исходные кнопки
        await callback.message.edit_reply_markup(reply_markup=callback.message.reply_markup)


@router.callback_query(F.data == "refund_cancel")
async def handle_refund_cancel(callback: CallbackQuery):
    """Отмена возврата денег"""
    # Восстанавливаем исходные кнопки
    await callback.message.edit_reply_markup(reply_markup=callback.message.reply_markup)
    await callback.answer("Отменено")
