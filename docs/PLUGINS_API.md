# 🔌 Документация по плагинам Starvell Cardinal

## Введение

Система плагинов Starvell Cardinal позволяет расширять функциональность бота без изменения основного кода. Плагины могут обрабатывать события, добавлять команды и выполнять автоматические действия.

### 🎯 Возможности плагинов

Плагины могут:

- 📨 **Обрабатывать события** - новые сообщения, заказы, старт/стоп бота
- 🤖 **Добавлять команды** - собственные команды в Telegram бот (`/mycommand`)
- 🔘 **Создавать UI** - inline-кнопки, меню, формы ввода
- 💾 **Хранить данные** - настройки, кэш, статистика в JSON файлах
- ⏰ **Запускать фоновые задачи** - периодические проверки, мониторинг
- 🌐 **Работать с API** - отправка сообщений, получение заказов, профилей
- 📊 **Собирать статистику** - логировать действия, считать метрики
- 🔧 **Интегрироваться с внешними сервисами** - SMM панели, payment API, etc.


## Структура плагина

Плагин - это обычный Python файл (.py) в папке `plugins/` с определёнными переменными и функциями.

### Минимальный плагин

```python
"""
Пример плагина
"""

# === МЕТАДАННЫЕ ===
NAME = "Мой плагин"
VERSION = "1.0.0"
DESCRIPTION = "Описание плагина"
AUTHOR = "Ваше имя"
UUID = "unique-plugin-id-12345"  # Уникальный ID

# === ФУНКЦИИ-ОБРАБОТЧИКИ ===
def on_init():
    """Вызывается при загрузке плагина"""
    print(f"Плагин {NAME} загружен!")

# === ПРИВЯЗКА К СОБЫТИЯМ ===
BIND_TO_PRE_INIT = [on_init]
```

## Обязательные переменные

| Переменная | Тип | Описание |
|-----------|------|----------|
| `NAME` | str | Название плагина |
| `VERSION` | str | Версия плагина |
| `DESCRIPTION` | str | Описание плагина |
| `AUTHOR` | str | Автор плагина |
| `UUID` | str | Уникальный ID плагина |
## События плагинов

### Жизненный цикл

#### `BIND_TO_PRE_INIT`
Вызывается **перед** инициализацией бота.

```python
def on_pre_init():
    print("Бот ещё не запущен")

BIND_TO_PRE_INIT = [on_pre_init]
```

#### `BIND_TO_INIT`
Вызывается **после** инициализации бота.

```python
async def on_init(bot, starvell, db, plugin_manager):
    """
    Args:
        bot: Объект бота Aiogram (Bot)
        starvell: StarvellService для работы с API
        db: Database для работы с хранилищем
        plugin_manager: PluginManager для управления плагинами
    """
    print("Бот запущен!")
    
    # Пример: получить список заказов
    orders = await starvell.get_orders()
    print(f"Активных заказов: {len(orders)}")

BIND_TO_INIT = [on_init]
```

#### `BIND_TO_DELETE`
Вызывается при **удалении** плагина.

```python
def on_delete():
    print("Плагин удаляется...")

BIND_TO_DELETE = [on_delete]
```

### События бота

#### `BIND_TO_NEW_MESSAGE`
Вызывается при получении нового сообщения.

```python
async def on_new_message(message_data: dict, starvell_service=None, *args, **kwargs):
    """
    Args:
        message_data (dict): Данные сообщения
        starvell_service (StarvellService): Сервис для работы с API
    
    Структура message_data:
    {
        'chat_id': str,       # ID чата (UUID)
        'author': str,        # ID автора сообщения (числовой, как строка)
        'content': str,       # Текст сообщения
        'message_id': str     # ID сообщения (UUID)
    }
    
    Пример:
    {
        'chat_id': '019b8386-1e8f-f31d-9e66-b05331f70af6',
        'author': '142989',
        'content': 'https://t.me/channel/123',
        'message_id': '019b9803-0ef6-eb89-eb81-0e72b7c2ff42'
    }
    """
    print(f"Новое сообщение от {message_data['author']}: {message_data['content']}")
    
    # Ответить на сообщение
    if starvell_service and message_data.get('chat_id'):
        await starvell_service.send_message(
            message_data['chat_id'],
            "Спасибо за сообщение!"
        )

BIND_TO_NEW_MESSAGE = [on_new_message]
```

#### `BIND_TO_INIT_MESSAGE`
Вызывается при первом опросе чатов после запуска (прогрев кэша, без уведомлений).

```python
async def on_init_message(event, starvell_service=None, bot=None, **kwargs):
    chat = event.chat  # ChatShortcut
    print(f"Известный чат: {chat.name} ({chat.id})")

BIND_TO_INIT_MESSAGE = [on_init_message]
```

#### `BIND_TO_MESSAGES_LIST_CHANGED`
Список чатов изменился (новое сообщение в одном из чатов).

```python
async def on_chats_changed(event, **kwargs):
    print("Список чатов Starvell обновился")

BIND_TO_MESSAGES_LIST_CHANGED = [on_chats_changed]
```

#### `BIND_TO_LAST_CHAT_MESSAGE_CHANGED`
Изменилось превью последнего сообщения в чате (до загрузки полной истории).

```python
async def on_last_message_changed(event, **kwargs):
    chat = event.chat
    print(f"Новая активность в чате {chat.name}: {chat.last_message_text[:50]}")

BIND_TO_LAST_CHAT_MESSAGE_CHANGED = [on_last_message_changed]
```

**FunPay-style обработчик** (с объектом `event`):

```python
async def on_new_message(bot, event):
    """Аналог FunPay Cardinal: bot + NewMessageEvent."""
    msg = event.message
    chat = event.chat
    print(f"{msg.author_username or msg.author_id}: {msg.content}")
    await bot.starvell.send_message(msg.chat_id, "Принято!")  # если есть обёртка

BIND_TO_NEW_MESSAGE = [on_new_message]
```

**Расширенный `message_data`:**

```python
{
    'chat_id': str,
    'author': str,              # ID отправителя
    'author_username': str,     # никнейм
    'author_roles': list,
    'content': str,
    'message_id': str,
    'created_at': str,
    'is_own': bool,
    'companion_id': str,        # ID собеседника в ЛС
    'companion_username': str,
    'order_id': str,            # если чат привязан к заказу
    'unread': bool,
    'chat': dict,               # сырой объект чата API
    'message': dict,            # сырой объект сообщения API
}
```

#### `BIND_TO_NEW_ORDER`
Вызывается при получении нового заказа.

```python
async def on_new_order(order_data: dict, starvell_service=None, *args, **kwargs):
    """
    Args:
        order_data (dict): Данные заказа
        starvell_service (StarvellService): Сервис для работы с API
    
    Структура order_data:
    {
        'id': str,                    # ID заказа (UUID)
        'buyer': str,                 # Имя покупателя
        'amount': float,              # Сумма заказа в рублях
        'lot_name': str,              # Название лота
        'lot_description': str,       # Описание лота
        'status': str,                # Статус заказа (CREATED, COMPLETED, etc.)
        'chat_id': str                # ID чата с покупателем (пусто если не найден)
    }
    
    Пример:
    {
        'id': '019b97fa-497b-3dd2-a041-da54f9378d8e',
        'buyer': 'Hackep',
        'amount': 1.08,
        'lot_name': 'АВТОНАКРУТКА ПРОСМОТРОВ TELEGRAM',
        'lot_description': '💜 Минимальный заказ: 50...',
        'status': 'CREATED',
        'chat_id': '019b8386-1e8f-f31d-9e66-b05331f70af6'
    }
    """
    print(f"📦 Новый заказ #{order_data['id']} от {order_data['buyer']}")
    
    # Отправить сообщение покупателю
    if starvell_service and order_data.get('chat_id'):
        await starvell_service.send_message(
            order_data['chat_id'],
            f"Здравствуйте! Спасибо за заказ {order_data['lot_name']}"
        )

BIND_TO_NEW_ORDER = [on_new_order]
```

## 🎮 Интеграция с Telegram Bot

Плагины могут полностью интегрироваться с Telegram ботом, добавляя команды, callback-кнопки и обработчики текста.

### 📋 Команды (COMMANDS)

Добавляйте собственные команды в бота через словарь `COMMANDS`.

**Базовая команда:**

```python
from aiogram import types
from aiogram.filters import Command

async def cmd_hello(message: types.Message):
    """Обработчик команды /hello"""
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n"
        f"Это команда из плагина."
    )

COMMANDS = {
    "hello": {
        "handler": cmd_hello,
        "description": "👋 Поздороваться с ботом",
        "filters": [Command("hello")]
    }
}
```

**Команда с параметрами:**

```python
async def cmd_calc(message: types.Message):
    """Калькулятор: /calc 5 + 3"""
    try:
        # message.text = "/calc 5 + 3"
        expression = message.text.replace("/calc", "").strip()
        result = eval(expression)  # Осторожно в продакшене!
        await message.answer(f"🔢 Результат: {result}")
    except:
        await message.answer("❌ Неверное выражение")

COMMANDS = {
    "calc": {
        "handler": cmd_calc,
        "description": "🔢 Калькулятор",
        "filters": [Command("calc")]
    }
}
```

**Множественные команды:**

```python
async def cmd_status(message: types.Message):
    await message.answer("✅ Плагин активен")

async def cmd_settings(message: types.Message):
    await message.answer("⚙️ Настройки плагина")

COMMANDS = {
    "mystatus": {
        "handler": cmd_status,
        "description": "✅ Статус плагина",
        "filters": [Command("mystatus")]
    },
    "mysettings": {
        "handler": cmd_settings,
        "description": "⚙️ Настройки",
        "filters": [Command("mysettings")]
    }
}
```

### 🔘 Callback кнопки (CALLBACKS)

Обрабатывайте нажатия на inline-кнопки через словарь `CALLBACKS`.

**Простой callback:**

```python
from aiogram import types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

async def cmd_menu(message: types.Message):
    """Команда с кнопками"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✨ Нажми меня",
            callback_data="myplugin:action"
        )],
        [InlineKeyboardButton(
            text="📊 Статистика",
            callback_data="myplugin:stats"
        )]
    ])
    
    await message.answer("Выберите действие:", reply_markup=keyboard)

async def handle_callback(callback: types.CallbackQuery):
    """Обработчик всех callback с префиксом myplugin:"""
    data = callback.data
    
    if data == "myplugin:action":
        await callback.answer("✅ Действие выполнено!")
        await callback.message.edit_text("Готово!")
    
    elif data == "myplugin:stats":
        await callback.answer()
        await callback.message.edit_text("📊 Статистика: 100 действий")

COMMANDS = {
    "menu": {
        "handler": cmd_menu,
        "description": "📋 Меню плагина",
        "filters": [Command("menu")]
    }
}

CALLBACKS = {
    "myplugin_handler": {
        "handler": handle_callback,
        "filter": F.data.startswith("myplugin:")
    }
}
```

**Callback с параметрами:**

```python
async def callback_with_params(callback: types.CallbackQuery):
    """Обработка callback вида: plugin:action:param"""
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    param = parts[2] if len(parts) > 2 else ""
    
    if action == "delete":
        await callback.answer(f"🗑 Удалено: {param}")
        await callback.message.delete()
    
    elif action == "edit":
        await callback.answer()
        await callback.message.edit_text(f"✏️ Редактирование: {param}")

CALLBACKS = {
    "plugin_callbacks": {
        "handler": callback_with_params,
        "filter": F.data.startswith("plugin:")
    }
}
```

### ✍️ Обработчики текста (TEXT_HANDLERS)

Перехватывайте текстовые сообщения для FSM (конечных автоматов) и пользовательского ввода.

**FSM для ввода данных:**

```python
from aiogram import types

# Глобальное хранилище состояний (в продакшене используйте Redis/DB)
_waiting_for_input = {}

async def cmd_setname(message: types.Message):
    """Команда для установки имени"""
    user_id = message.from_user.id
    _waiting_for_input[user_id] = "name"
    
    await message.answer(
        "📝 Введите новое имя:\n\n"
        "Отправьте любой текст или /cancel для отмены"
    )

async def handle_text_input(message: types.Message):
    """Обработчик текстовых сообщений"""
    user_id = message.from_user.id
    
    if user_id not in _waiting_for_input:
        return  # Игнорируем, если не ждём ввода
    
    state = _waiting_for_input[user_id]
    
    if state == "name":
        new_name = message.text.strip()
        
        # Сохраняем имя (в продакшене - в БД)
        await message.answer(f"✅ Имя изменено на: {new_name}")
        
        # Очищаем состояние
        del _waiting_for_input[user_id]

async def cmd_cancel(message: types.Message):
    """Отмена ввода"""
    user_id = message.from_user.id
    if user_id in _waiting_for_input:
        del _waiting_for_input[user_id]
        await message.answer("❌ Отменено")
    else:
        await message.answer("Нечего отменять")

COMMANDS = {
    "setname": {
        "handler": cmd_setname,
        "description": "📝 Установить имя",
        "filters": [Command("setname")]
    },
    "cancel": {
        "handler": cmd_cancel,
        "description": "❌ Отменить ввод",
        "filters": [Command("cancel")]
    }
}

TEXT_HANDLERS = {
    "input_handler": {
        "handler": handle_text_input,
        "filter": lambda m: m.from_user.id in _waiting_for_input
    }
}
```

**Множественные этапы ввода:**

```python
# Состояния: None -> "waiting_url" -> "waiting_quantity" -> None
_user_states = {}

async def cmd_order(message: types.Message):
    """Начать создание заказа"""
    user_id = message.from_user.id
    _user_states[user_id] = {
        "state": "waiting_url",
        "data": {}
    }
    
    await message.answer("🔗 Отправьте ссылку:")

async def multi_step_handler(message: types.Message):
    """Обработка многоэтапного ввода"""
    user_id = message.from_user.id
    
    if user_id not in _user_states:
        return
    
    state_info = _user_states[user_id]
    state = state_info["state"]
    
    if state == "waiting_url":
        # Сохраняем URL
        state_info["data"]["url"] = message.text
        state_info["state"] = "waiting_quantity"
        await message.answer("🔢 Теперь отправьте количество:")
    
    elif state == "waiting_quantity":
        # Сохраняем количество
        try:
            quantity = int(message.text)
            url = state_info["data"]["url"]
            
            await message.answer(
                f"✅ Заказ создан!\n"
                f"🔗 URL: {url}\n"
                f"🔢 Количество: {quantity}"
            )
            
            # Очищаем состояние
            del _user_states[user_id]
        except ValueError:
            await message.answer("❌ Введите число")

TEXT_HANDLERS = {
    "multi_step": {
        "handler": multi_step_handler,
        "filter": lambda m: m.from_user.id in _user_states
    }
}
```

### 🎯 Фильтры и условия

Используйте встроенные фильтры aiogram для тонкой настройки:

```python
from aiogram import F
from aiogram.filters import Command, CommandStart

# Только админы
async def admin_only(message: types.Message):
    await message.answer("Только для админов")

COMMANDS = {
    "admin": {
        "handler": admin_only,
        "description": "👑 Админская команда",
        "filters": [
            Command("admin"),
            lambda m: m.from_user.id in [123456789, 987654321]  # ID админов
        ]
    }
}

# Только приватные чаты
CALLBACKS = {
    "private_only": {
        "handler": some_handler,
        "filter": F.data == "button" & F.message.chat.type == "private"
    }
}

# Только текстовые сообщения с определённым содержимым
TEXT_HANDLERS = {
    "contains_hello": {
        "handler": handle_hello,
        "filter": F.text.contains("привет") | F.text.contains("hello")
    }
}
```

### 📦 Полный пример плагина с UI

```python
"""
Пример плагина с полным UI
"""

NAME = "Example Plugin"
VERSION = "1.0.0"
DESCRIPTION = "Пример с командами и кнопками"
AUTHOR = "@author"
UUID = "example-plugin-uuid"

from aiogram import types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

_plugin_enabled = True

async def cmd_start(message: types.Message):
    """Главное меню плагина"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Включить", callback_data="ex:enable"),
            InlineKeyboardButton(text="❌ Выключить", callback_data="ex:disable")
        ],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="ex:stats")]
    ])
    
    status = "включён" if _plugin_enabled else "выключен"
    await message.answer(
        f"⚙️ <b>Example Plugin</b>\n\n"
        f"Статус: {status}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def handle_callbacks(callback: types.CallbackQuery):
    """Обработка всех кнопок"""
    global _plugin_enabled
    
    action = callback.data.replace("ex:", "")
    
    if action == "enable":
        _plugin_enabled = True
        await callback.answer("✅ Включено")
        await callback.message.edit_text(
            "⚙️ <b>Example Plugin</b>\n\nСтатус: включён",
            parse_mode="HTML"
        )
    
    elif action == "disable":
        _plugin_enabled = False
        await callback.answer("❌ Выключено")
        await callback.message.edit_text(
            "⚙️ <b>Example Plugin</b>\n\nСтатус: выключен",
            parse_mode="HTML"
        )
    
    elif action == "stats":
        await callback.answer()
        await callback.message.edit_text("📊 Статистика: всё отлично!")

COMMANDS = {
    "example": {
        "handler": cmd_start,
        "description": "⚙️ Example Plugin",
        "filters": [Command("example")]
    }
}

CALLBACKS = {
    "example_cb": {
        "handler": handle_callbacks,
        "filter": F.data.startswith("ex:")
    }
}
```

## Настройки плагина

Плагины могут иметь собственные настройки.

```python
# Настройки по умолчанию
DEFAULT_SETTINGS = {
    "enabled": True,
    "interval": 60,
    "max_retries": 3
}

# Функция для получения настроек
def get_settings():
    """Получить настройки плагина"""
    # Здесь можно загрузить настройки из файла
    return DEFAULT_SETTINGS

# Функция для сохранения настроек
def save_settings(settings):
    """Сохранить настройки плагина"""
    # Здесь можно сохранить настройки в файл
    pass
```

## 💾 Хранение данных плагина

Каждый плагин может сохранять свои данные в отдельной директории.

### Структура хранилища

```
storage/
└── plugins/
    └── {UUID}/              # Директория плагина по UUID
        ├── settings.json    # Настройки
        ├── data.json        # Основные данные
        └── cache.json       # Кэш
```

### Работа с JSON файлами

```python
import json
from pathlib import Path

# UUID плагина
UUID = "my-plugin-uuid-12345"

# Пути к файлам
STORAGE_DIR = Path(f"storage/plugins/{UUID}")
SETTINGS_FILE = STORAGE_DIR / "settings.json"
DATA_FILE = STORAGE_DIR / "data.json"

def ensure_storage():
    """Создать директорию если не существует"""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

def load_json(filepath: Path, default=None):
    """Загрузить JSON файл"""
    if default is None:
        default = {}
    
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки {filepath}: {e}")
    
    return default

def save_json(filepath: Path, data):
    """Сохранить JSON файл"""
    ensure_storage()
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка сохранения {filepath}: {e}")

# Использование
def on_init():
    ensure_storage()
    
    # Загрузить настройки
    settings = load_json(SETTINGS_FILE, {"enabled": True})
    print(f"Настройки: {settings}")
    
    # Изменить и сохранить
    settings["last_run"] = "2026-01-11"
    save_json(SETTINGS_FILE, settings)

BIND_TO_INIT = [on_init]
```

### Хранение списков и очередей

```python
from typing import List, Dict

# Хранение заказов
ORDERS_FILE = STORAGE_DIR / "orders.json"

def add_order(order_data: Dict):
    """Добавить заказ в список"""
    orders = load_json(ORDERS_FILE, [])
    orders.append(order_data)
    save_json(ORDERS_FILE, orders)

def get_pending_orders() -> List[Dict]:
    """Получить незавершённые заказы"""
    orders = load_json(ORDERS_FILE, [])
    return [o for o in orders if o.get("status") == "pending"]

def remove_order(order_id: str):
    """Удалить заказ из списка"""
    orders = load_json(ORDERS_FILE, [])
    orders = [o for o in orders if o.get("id") != order_id]
    save_json(ORDERS_FILE, orders)

# Использование в обработчике
async def on_new_order(order_data: dict, **kwargs):
    add_order({
        "id": order_data["id"],
        "buyer": order_data["buyer"],
        "status": "pending",
        "created_at": "2026-01-11 12:00:00"
    })
```

### Хранение словарей (key-value)

```python
# Маппинг: chat_id -> order_id
MAPPING_FILE = STORAGE_DIR / "chat_to_order.json"

def map_chat_to_order(chat_id: str, order_id: str):
    """Связать чат с заказом"""
    mapping = load_json(MAPPING_FILE, {})
    mapping[chat_id] = order_id
    save_json(MAPPING_FILE, mapping)

def get_order_by_chat(chat_id: str) -> str:
    """Получить order_id по chat_id"""
    mapping = load_json(MAPPING_FILE, {})
    return mapping.get(chat_id)

# Использование
async def on_new_order(order_data: dict, **kwargs):
    chat_id = order_data.get("chat_id")
    if chat_id:
        map_chat_to_order(chat_id, order_data["id"])

async def on_new_message(message_data: dict, **kwargs):
    chat_id = message_data["chat_id"]
    order_id = get_order_by_chat(chat_id)
    
    if order_id:
        print(f"Сообщение для заказа {order_id}")
```

### Кэширование данных

```python
from datetime import datetime, timedelta

CACHE_FILE = STORAGE_DIR / "cache.json"

def cache_set(key: str, value: any, ttl_seconds: int = 3600):
    """Сохранить в кэш с TTL"""
    cache = load_json(CACHE_FILE, {})
    
    expires_at = (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat()
    
    cache[key] = {
        "value": value,
        "expires_at": expires_at
    }
    
    save_json(CACHE_FILE, cache)

def cache_get(key: str) -> any:
    """Получить из кэша (None если истёк)"""
    cache = load_json(CACHE_FILE, {})
    
    if key not in cache:
        return None
    
    entry = cache[key]
    expires_at = datetime.fromisoformat(entry["expires_at"])
    
    if datetime.now() > expires_at:
        # Удаляем истёкший кэш
        del cache[key]
        save_json(CACHE_FILE, cache)
        return None
    
    return entry["value"]

# Использование
async def get_user_profile(user_id: str, starvell_service):
    """Получить профиль с кэшированием"""
    cached = cache_get(f"profile_{user_id}")
    if cached:
        return cached
    
    # Запрашиваем через API
    profile = await starvell_service.get_user_profile(user_id)
    
    # Кэшируем на 1 час
    cache_set(f"profile_{user_id}", profile, ttl_seconds=3600)
    
    return profile
```

### Статистика и логирование

```python
STATS_FILE = STORAGE_DIR / "statistics.json"

def add_stat_entry(action: str, details: Dict = None):
    """Добавить запись в статистику"""
    stats = load_json(STATS_FILE, [])
    
    entry = {
        "action": action,
        "timestamp": datetime.now().isoformat(),
        "details": details or {}
    }
    
    stats.append(entry)
    save_json(STATS_FILE, stats)

def get_stats_summary(days: int = 7) -> Dict:
    """Получить сводку за период"""
    stats = load_json(STATS_FILE, [])
    
    cutoff = datetime.now() - timedelta(days=days)
    recent = [
        s for s in stats 
        if datetime.fromisoformat(s["timestamp"]) >= cutoff
    ]
    
    return {
        "total": len(recent),
        "by_action": {}  # Можно добавить группировку
    }

# Использование
async def on_new_order(order_data: dict, **kwargs):
    add_stat_entry("order_created", {
        "order_id": order_data["id"],
        "amount": order_data["amount"]
    })
```

## Доступ к API бота

Плагины могут использовать API Starvell через параметр `starvell_service` в обработчиках событий.

## ⏰ Фоновые задачи и планировщики

Плагины могут выполнять периодические задачи и асинхронные операции.

### Создание фоновой задачи

```python
import asyncio
import logging

logger = logging.getLogger("MyPlugin")

_background_task = None
_is_running = False

async def background_worker():
    """Фоновая задача которая выполняется каждые N секунд"""
    global _is_running
    
    while _is_running:
        try:
            logger.info("⏰ Выполняю периодическую задачу...")
            
            # Ваша логика
            await asyncio.sleep(1)  # Симуляция работы
            
            logger.info("✅ Задача выполнена")
            
            # Ждём перед следующим запуском
            await asyncio.sleep(60)  # 60 секунд
            
        except asyncio.CancelledError:
            logger.info("🛑 Задача остановлена")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка в фоновой задаче: {e}", exc_info=True)
            await asyncio.sleep(60)

def on_init(bot=None, starvell=None, **kwargs):
    """Запуск при инициализации"""
    global _background_task, _is_running
    
    _is_running = True
    _background_task = asyncio.create_task(background_worker())
    logger.info("🚀 Фоновая задача запущена")

def on_delete():
    """Остановка при удалении плагина"""
    global _background_task, _is_running
    
    _is_running = False
    
    if _background_task:
        _background_task.cancel()
    
    logger.info("🛑 Фоновая задача остановлена")

BIND_TO_INIT = [on_init]
BIND_TO_DELETE = [on_delete]
```

### Проверка статусов заказов

```python
import asyncio
from datetime import datetime

_checker_task = None
_starvell = None
_active_orders = {}  # order_id -> order_data

async def order_status_checker():
    """Проверка статусов заказов каждые 60 секунд"""
    global _starvell, _active_orders
    
    while True:
        try:
            if not _active_orders:
                await asyncio.sleep(60)
                continue
            
            logger.info(f"🔍 Проверяю {len(_active_orders)} заказов...")
            
            for order_id, order_data in list(_active_orders.items()):
                # Получаем актуальный статус
                details = await _starvell.get_order_details(order_id)
                status = details["pageProps"]["order"]["status"]
                
                if status == "COMPLETED":
                    logger.info(f"✅ Заказ {order_id} завершён")
                    
                    # Отправляем уведомление
                    chat_id = order_data.get("chat_id")
                    if chat_id:
                        await _starvell.send_message(
                            chat_id,
                            f"✅ Заказ завершён! Спасибо за покупку."
                        )
                    
                    # Удаляем из отслеживания
                    del _active_orders[order_id]
                
                elif status == "CANCELLED":
                    logger.info(f"❌ Заказ {order_id} отменён")
                    del _active_orders[order_id]
            
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Ошибка проверки статусов: {e}")
            await asyncio.sleep(60)

async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    """Добавляем заказ в отслеживание"""
    global _active_orders
    
    _active_orders[order_data["id"]] = order_data
    logger.info(f"📦 Заказ {order_data['id']} добавлен в отслеживание")

def on_init(bot=None, starvell=None, **kwargs):
    """Запуск чекера"""
    global _checker_task, _starvell
    
    _starvell = starvell
    _checker_task = asyncio.create_task(order_status_checker())
    logger.info("🚀 Чекер статусов запущен")

def on_delete():
    """Остановка чекера"""
    global _checker_task
    
    if _checker_task:
        _checker_task.cancel()
    
    logger.info("🛑 Чекер статусов остановлен")

BIND_TO_INIT = [on_init]
BIND_TO_DELETE = [on_delete]
BIND_TO_NEW_ORDER = [on_new_order]
```

### Множественные задачи

```python
_tasks = []

async def task_1():
    """Задача 1: каждые 30 секунд"""
    while True:
        await asyncio.sleep(30)
        logger.info("Задача 1 выполнена")

async def task_2():
    """Задача 2: каждые 60 секунд"""
    while True:
        await asyncio.sleep(60)
        logger.info("Задача 2 выполнена")

def on_init(**kwargs):
    """Запуск всех задач"""
    global _tasks
    
    _tasks.append(asyncio.create_task(task_1()))
    _tasks.append(asyncio.create_task(task_2()))
    
    logger.info(f"🚀 Запущено {len(_tasks)} задач")

def on_delete():
    """Остановка всех задач"""
    global _tasks
    
    for task in _tasks:
        task.cancel()
    
    _tasks.clear()
    logger.info("🛑 Все задачи остановлены")

BIND_TO_INIT = [on_init]
BIND_TO_DELETE = [on_delete]
```

### Динамический интервал

```python
_interval = 60  # Начальный интервал

async def adaptive_task():
    """Задача с адаптивным интервалом"""
    global _interval
    
    while True:
        try:
            # Выполняем работу
            result = await do_some_work()
            
            # Адаптируем интервал
            if result == "много работы":
                _interval = 30  # Чаще проверяем
            else:
                _interval = 120  # Реже проверяем
            
            logger.info(f"⏰ Следующая проверка через {_interval}с")
            await asyncio.sleep(_interval)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await asyncio.sleep(60)
```

### Обработка ошибок и retry

```python
async def task_with_retry():
    """Задача с повторными попытками при ошибке"""
    max_retries = 3
    retry_delay = 5
    
    while True:
        for attempt in range(max_retries):
            try:
                # Выполняем рискованную операцию
                await risky_operation()
                break  # Успех - выходим из retry loop
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"⚠️ Попытка {attempt + 1}/{max_retries} не удалась: {e}"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"❌ Все {max_retries} попытки провалены")
        
        # Ждём перед следующим циклом
        await asyncio.sleep(60)
```

### Использование APScheduler (продвинутое)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_scheduler = None

async def daily_task():
    """Задача выполняется раз в день в 3:00"""
    logger.info("📅 Выполняю ежедневную задачу")

async def hourly_task():
    """Задача выполняется каждый час"""
    logger.info("⏰ Выполняю часовую задачу")

def on_init(**kwargs):
    """Настройка планировщика"""
    global _scheduler
    
    _scheduler = AsyncIOScheduler()
    
    # Каждый день в 03:00
    _scheduler.add_job(
        daily_task,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_task"
    )
    
    # Каждый час
    _scheduler.add_job(
        hourly_task,
        trigger="interval",
        hours=1,
        id="hourly_task"
    )
    
    _scheduler.start()
    logger.info("🚀 Планировщик запущен")

def on_delete():
    """Остановка планировщика"""
    global _scheduler
    
    if _scheduler:
        _scheduler.shutdown()
    
    logger.info("🛑 Планировщик остановлен")

BIND_TO_INIT = [on_init]
BIND_TO_DELETE = [on_delete]
```

### StarvellService API

Объект `StarvellService` предоставляет методы для работы с платформой Starvell.com:

#### `send_message(chat_id: str, content: str) -> dict`

Отправить сообщение в чат.

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    if starvell_service and order_data.get('chat_id'):
        result = await starvell_service.send_message(
            chat_id=order_data['chat_id'],
            content="Здравствуйте! Спасибо за заказ!"
        )
        # result - dict с ответом от API
```

**Возвращает:**
```python
{
    "success": True,  # или False при ошибке
    # ... другие поля от API
}
```

#### `get_order_details(order_id: str) -> dict`

Получить детальную информацию о заказе.

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    if starvell_service:
        details = await starvell_service.get_order_details(order_data['id'])
```

**Возвращает:**
```python
{
    "pageProps": {
        "order": {
            "id": "019b97fa-497b-3dd2-a041-da54f9378d8e",
            "status": "CREATED",
            "basePrice": 100,          # Цена в копейках
            "totalPrice": 108,         # Итого в копейках (с комиссией)
            "buyerId": 142989,         # ID покупателя (число)
            "sellerId": 7970,          # ID продавца (число)
            "offerId": 141378,         # ID лота
            "quantity": 1000,          # Количество единиц товара
            "createdAt": "2026-01-07T10:22:01.068Z",
            "buyer": {
                "id": 142989,
                "username": "Hackep",
                "isOnline": True,
                "avatar": "uuid-here",
                # ... другие поля профиля
            },
            "seller": {
                "id": 7970,
                "username": "Kirito",
                # ... другие поля профиля
            },
            "offerDetails": {
                "game": {"id": 14, "name": "Telegram"},
                "category": {"id": 175, "name": "Услуги"},
                "descriptions": {
                    "rus": {
                        "description": "Полное описание...",
                        "briefDescription": "Краткое описание"
                    }
                },
                # ... другие поля лота
            }
        },
        "chat": {
            "id": "019b8386-1e8f-f31d-9e66-b05331f70af6",  # UUID чата!
            # ... другие поля чата
        },
        "messages": [],  # Массив сообщений
        # ... другие поля
    },
    "__N_SSP": True
}
```

**Важно:** `chat.id` находится в `pageProps.chat.id`, а не в `pageProps.order`!

#### `get_orders() -> list`

Получить список заказов.

```python
async def on_init(bot, starvell, db, plugin_manager):
    orders = await starvell.get_orders()
    for order in orders:
        print(f"Заказ: {order['id']}")
```

**Возвращает:**
```python
[
    {
        "id": "order-uuid",
        "status": "CREATED",
        "totalPrice": 108,
        "buyer": {...},
        "seller": {...},
        # ... другие поля
    },
    # ... остальные заказы
]
```

#### `refund_order(order_id: str) -> dict`

Вернуть деньги за заказ.

```python
async def handle_refund(order_id: str, starvell_service):
    result = await starvell_service.refund_order(order_id)
    # result содержит результат операции
```

#### `find_chat_by_user_id(user_id: str) -> str | None`

Найти ID чата с конкретным пользователем по его ID.

```python
async def find_user_chat(starvell_service):
    chat_id = await starvell_service.find_chat_by_user_id("142989")
    if chat_id:
        await starvell_service.send_message(chat_id, "Привет!")
```

**Возвращает:** UUID чата (строка) или `None` если чат не найден.

### Примеры использования

#### Отправка приветствия при новом заказе

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    """Отправить приветствие покупателю"""
    if not starvell_service:
        return
    
    # Если chat_id уже есть в order_data
    if order_data.get('chat_id'):
        await starvell_service.send_message(
            order_data['chat_id'],
            f"👋 Здравствуйте!\n\n"
            f"📦 Спасибо за заказ: {order_data['lot_name']}\n"
            f"💰 Сумма: {order_data['amount']}₽"
        )
    else:
        # Получить детали заказа, чтобы найти chat_id
        details = await starvell_service.get_order_details(order_data['id'])
        page_props = details.get("pageProps", {})
        chat_data = page_props.get("chat", {})
        chat_id = chat_data.get("id")
        
        if chat_id:
            await starvell_service.send_message(chat_id, "Привет!")
```

#### Обработка сообщений с автоответом

```python
async def on_new_message(message_data: dict, starvell_service=None, **kwargs):
    """Автоматически ответить на сообщение"""
    if not starvell_service:
        return
    
    content = message_data.get('content', '').lower()
    chat_id = message_data.get('chat_id')
    
    if 'помощь' in content or 'help' in content:
        await starvell_service.send_message(
            chat_id,
            "ℹ️ Для помощи напишите администратору @support"
        )
```

## Логирование

Используйте стандартный модуль `logging` для вывода логов.

```python
import logging

logger = logging.getLogger(__name__)

def on_init():
    logger.info("✅ Плагин инициализирован")
    logger.debug("Отладочная информация")
    logger.warning("⚠️ Предупреждение")
    logger.error("❌ Ошибка")

BIND_TO_INIT = [on_init]
```

## Пример полного плагина

```python
"""
Плагин автоответчика
Автоматически отвечает на сообщения с определённым текстом
"""

import logging

logger = logging.getLogger(__name__)

# === МЕТАДАННЫЕ ===
NAME = "Автоответчик"
VERSION = "1.0.0"
DESCRIPTION = "Автоматически отвечает на сообщения"
AUTHOR = "@knowtake"
UUID = "auto-reply-plugin-001"
# === НАСТРОЙКИ ===
TRIGGER_WORDS = ["помощь", "help", "info"]
AUTO_REPLY = "Здравствуйте! Я сейчас не могу ответить. Напишите позже."

# === ОБРАБОТЧИКИ ===
def on_init():
    logger.info(f"✅ {NAME} v{VERSION} загружен")

async def on_new_message(message_data, starvell_service=None, *args):
    """Проверяем сообщение и отвечаем если нужно"""
    content = message_data.get('content', '').lower()
    
    # Проверяем триггерные слова
    if any(word in content for word in TRIGGER_WORDS):
        chat_id = message_data.get('chat_id')
        
        if starvell_service and chat_id:
            try:
                await starvell_service.send_message(chat_id, AUTO_REPLY)
                logger.info(f"📤 Отправлен автоответ в чат {chat_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки автоответа: {e}")

# === ПРИВЯЗКИ ===
BIND_TO_INIT = [on_init]
BIND_TO_NEW_MESSAGE = [on_new_message]
```

## Установка плагина

1. Скопируйте `.py` файл плагина в папку `plugins/`
2. Перезапустите бота или используйте команду `/start`
3. Плагин автоматически загрузится




## Примеры плагинов

Смотрите `plugins/example_plugin.py` и `plugins/AutoSmm.py` для примеров реализации всех возможностей.

## Полезные советы

### 1. Всегда используйте async/await

Все обработчики событий должны быть асинхронными:

```python
# ✅ Правильно
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    await starvell_service.send_message(...)

# ❌ Неправильно
def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    # Синхронная функция не может использовать await
    pass
```

### 2. Проверяйте наличие starvell_service

Всегда проверяйте, что `starvell_service` передан:

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    if not starvell_service:
        logger.warning("starvell_service не передан!")
        return
    
    # Теперь безопасно использовать
    await starvell_service.send_message(...)
```

### 3. Обрабатывайте исключения

Всегда оборачивайте код в try/except:

```python
async def on_new_message(message_data: dict, starvell_service=None, **kwargs):
    try:
        chat_id = message_data.get('chat_id')
        if starvell_service and chat_id:
            await starvell_service.send_message(chat_id, "Привет!")
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
```

### 4. Используйте логирование

Логируйте важные события и ошибки:

```python
import logging

logger = logging.getLogger(__name__)

async def on_new_order(order_data: dict, **kwargs):
    logger.info(f"📦 Получен заказ {order_data['id']}")
    logger.debug(f"Детали: {order_data}")  # Только в режиме отладки
```

### 5. Сохраняйте данные правильно

Используйте JSON для хранения данных плагина:

```python
import json
from pathlib import Path

PLUGIN_DATA_FILE = Path("storage/my_plugin_data.json")

def save_data(data: dict):
    """Сохранить данные плагина"""
    PLUGIN_DATA_FILE.parent.mkdir(exist_ok=True)
    with open(PLUGIN_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_data() -> dict:
    """Загрузить данные плагина"""
    if not PLUGIN_DATA_FILE.exists():
        return {}
    with open(PLUGIN_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)
```

## FAQ

### Как получить chat_id для отправки сообщений?

**Вариант 1:** Использовать `order_data['chat_id']` (если уже есть):

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    chat_id = order_data.get('chat_id')
    if chat_id and starvell_service:
        await starvell_service.send_message(chat_id, "Привет!")
```

**Вариант 2:** Получить из деталей заказа:

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    if not starvell_service:
        return
    
    # Получаем полные детали заказа
    details = await starvell_service.get_order_details(order_data['id'])
    page_props = details.get("pageProps", {})
    
    # chat находится в pageProps.chat, а НЕ в pageProps.order!
    chat_data = page_props.get("chat", {})
    chat_id = chat_data.get("id")
    
    if chat_id:
        await starvell_service.send_message(chat_id, "Сообщение")
```

### Почему message_data['author'] это число, а не имя?

`author` содержит **ID покупателя** (buyerId), а не имя. Чтобы получить имя:

**Вариант 1:** Сохранить соответствие при создании заказа:

```python
# В on_new_order сохраняем buyer_id
order_info = {
    'buyer': order_data['buyer'],      # "Hackep"
    'buyer_id': str(buyer_id)          # "142989"
}

# В on_new_message ищем по author
author = message_data['author']  # "142989"
# Находим заказ где buyer_id == author
```

**Вариант 2:** Получить из деталей заказа:

```python
details = await starvell_service.get_order_details(order_id)
buyer = details["pageProps"]["order"]["buyer"]
buyer_name = buyer["username"]  # "Hackep"
buyer_id = buyer["id"]          # 142989
```

### Как обрабатывать количество товара?

Количество хранится в `order.quantity` в деталях заказа:

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    # Получаем детали
    details = await starvell_service.get_order_details(order_data['id'])
    order_info = details["pageProps"]["order"]
    
    quantity = order_info.get("quantity", 1)  # Количество единиц
    
    # Если в описании есть множитель (например #Quan:10)
    import re
    lot_description = order_data['lot_description']
    match_quan = re.search(r'#Quan:\s*(\d+)', lot_description)
    quan_per_unit = int(match_quan.group(1)) if match_quan else 1
    
    # Итоговое количество
    final_quantity = quantity * quan_per_unit
    print(f"Заказано: {quantity} × {quan_per_unit} = {final_quantity}")
```

### Как отключить плагин программно?

Используйте `plugin_manager`:

```python
async def on_init(bot, starvell, db, plugin_manager):
    # Отключить себя
    plugin_manager.disable_plugin("my-plugin-uuid")
    
    # Отключить другой плагин
    plugin_manager.disable_plugin("other-plugin-uuid")
```

## 💡 Лучшие практики

### Безопасность

**Валидация входных данных:**

```python
async def on_new_message(message_data: dict, **kwargs):
    content = message_data.get("content", "").strip()
    
    # Проверка на пустоту
    if not content:
        return
    
    # Валидация URL
    import re
    url_pattern = r'^https?://'
    if not re.match(url_pattern, content):
        return  # Не URL
    
    # Защита от SQL injection (если используете SQL)
    # Используйте параметризованные запросы
```

**Безопасное хранение ключей:**

```python
# ❌ ПЛОХО - ключи в коде
API_KEY = "secret123"

# ✅ ХОРОШО - ключи в настройках
def get_api_key():
    settings = load_json(SETTINGS_FILE, {})
    return settings.get("api_key", "")
```

### Производительность

**Используйте async/await правильно:**

```python
# ❌ ПЛОХО - блокирующие операции
def blocking_operation():
    import time
    time.sleep(5)  # Блокирует весь event loop!

# ✅ ХОРОШО - асинхронные операции
async def async_operation():
    await asyncio.sleep(5)  # Не блокирует
```

**Кэшируйте API запросы:**

```python
# ✅ Кэшируем профили на 1 час
async def get_user_profile_cached(user_id: str, starvell):
    cached = cache_get(f"profile_{user_id}")
    if cached:
        return cached
    
    profile = await starvell.get_user_profile(user_id)
    cache_set(f"profile_{user_id}", profile, ttl_seconds=3600)
    return profile
```

**Батчинг операций:**

```python
# ❌ ПЛОХО - много запросов
for order_id in order_ids:
    await process_order(order_id)

# ✅ ХОРОШО - батчинг
batch_size = 10
for i in range(0, len(order_ids), batch_size):
    batch = order_ids[i:i + batch_size]
    await asyncio.gather(*[process_order(oid) for oid in batch])
```

### Обработка ошибок

**Всегда используйте try-except:**

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    try:
        # Ваш код
        result = await process_order(order_data)
    except KeyError as e:
        logger.error(f"Отсутствует поле: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}", exc_info=True)
```

### Чистый код

**Разделяйте логику:**

```python
# ❌ ПЛОХО - всё в одной функции
async def on_new_order(order_data: dict, **kwargs):
    # 200 строк кода...
    pass

# ✅ ХОРОШО - разделённая логика
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    """Главный обработчик"""
    if not validate_order(order_data):
        return
    
    await send_greeting(order_data, starvell_service)
    await save_to_storage(order_data)
    await notify_admins(order_data)

def validate_order(order_data: dict) -> bool:
    """Валидация заказа"""
    return all([
        order_data.get("id"),
        order_data.get("buyer"),
        order_data.get("chat_id")
    ])

async def send_greeting(order_data: dict, starvell):
    """Отправка приветствия"""
    # ...
```



### Тестирование

**Создавайте тестовые функции:**

```python
async def test_order_processing():
    """Тест обработки заказа"""
    test_order = {
        "id": "test-123",
        "buyer": "TestUser",
        "amount": 100.0,
        "chat_id": "test-chat"
    }
    
    result = await process_order(test_order)
    assert result is not None
    logger.info("✅ Тест пройден")

# Вызов в on_init для отладки
async def on_init(**kwargs):
    if DEBUG_MODE:
        await test_order_processing()
```

### Документация

**Документируйте функции:**

```python
async def process_order(order_data: dict, starvell_service) -> bool:
    """
    Обработка заказа и отправка товара
    
    Args:
        order_data (dict): Данные заказа с полями id, buyer, amount
        starvell_service: Сервис для работы с API Starvell
    
    Returns:
        bool: True если успешно, False при ошибке
    
    Raises:
        ValueError: Если отсутствуют обязательные поля
        APIError: Если ошибка API
    
    Example:
        >>> await process_order({"id": "123", ...}, starvell)
        True
    """
    pass
```


## 📚 Полезные ссылки

- **Aiogram Documentation**: <https://docs.aiogram.dev/>
- **Python Async/Await**: <https://docs.python.org/3/library/asyncio.html>
- **Автор:** @knowtake

## Поддержка

- Telegram: @knowtake
- Telegram: @starvellingbot

---

**Starvell Cardinal** - мощная система автоматизации для Starvell.com
