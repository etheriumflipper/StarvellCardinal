# 🤖 Starvell Cardinal
open-source Telegram bot на Python (aiogram) для автоматизации маркетплейса Starvell.com:
автодоставка товаров, управление лотами,
мониторинг заказов и продаж. 
> An open-source Python Telegram bot for automating Starvell marketplace workflows.

**Автор:** @embedium | **Лицензия:** MIT

---

## 🌟 Основные возможности

### 🚚 Автоматизация доставки
- **AutoDelivery** — автоматическая выдача товаров после покупки
- **AutoRestore** — восстановление активности лотов
- **AutoRaise** — автоматический поднос лотов в топ
- **AutoUpdate** — обновление информации лотов
- **AutoTicket** — автоматическая отправка тикетов для неподтвержденных заказов

### 📊 Управление аккаунтом
- Управление товарами и лотами
- Отслеживание заказов и сообщений
- Система логирования и уведомлений
- Сохранение истории операций

### 🔌 Расширяемость
- **Система плагинов** для добавления новых функций
- Различные события жизненного цикла (инициализация, удаление)
- Обработка событий бота (новые сообщения, заказы)
- Полная документация API

### 🔐 Безопасность
- Аутентификация через куки сессии
- Мидлвары для проверки прав
- Защита от несанкционированного доступа
- Хранение конфиденциальных данных в локальной конфигурации

---

## 📋 Требования

- **Python** >= 3.9
- **pip** — менеджер пакетов Python
- **Интернет-соединение** для работы с API Starvell.com и Telegram

### Зависимости

```
aiogram>=3.3.0          # Telegram Bot API
aiohttp>=3.9.0          # HTTP клиент
apscheduler>=3.10.0     # Планировщик задач
colorama>=0.4.6         # Цветной вывод в консоль
```

---

## 🚀 Установка

### Windows

1. Установите Python 3.9 или выше с [python.org](https://www.python.org/downloads/)
2. Скачайте проект:
   ```bash
   git clone <REPOSITORY_URL>
   cd Starvell-cardinal
   ```
3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
4. Запустите бота:
   ```bash
   python main.py
   ```

### Linux (Ubuntu/Debian)

1. Клонируйте репозиторий:
   ```bash
   git clone <REPOSITORY_URL>
   cd Starvell-cardinal
   ```

2. Запустите установщик:
   ```bash
   sudo bash install.sh
   ```

3. После установки используйте systemd:
   ```bash
   sudo systemctl status starvell-cardinal
   sudo systemctl restart starvell-cardinal
   sudo journalctl -u starvell-cardinal -f
   ```

### Установка через URL (Linux)

Можно установить одной командой:

```bash
git clone <REPOSITORY_URL> && cd Starvell-cardinal && sudo bash install.sh
```

### Первый запуск

Во время `install.sh` откроется мастер настройки, который попросит:
1. **Bot Token** — получите у [@BotFather](https://t.me/BotFather)
2. **Пароль** — для защиты доступа к боту
3. **Session Cookie** — из браузера на starvell.com (F12 → Application → Cookies → session)

После настройки установщик создаст и запустит `systemd`-сервис автоматически.

---

## ⚙️ Конфигурация

Конфигурация хранится в файле `configs/_main.cfg` (создаётся автоматически при первом запуске).

### Основные параметры

```ini
[Starvell]
# Ваша сессия (куки) на сайте Starvell.com
session_cookie = your_session_here

# User-Agent браузера
user_agent = Mozilla/5.0...

# Включение функций (0 = отключено, 1 = включено)
autoRaise = 0          # Автоматический поднос лотов
autoDelivery = 0       # Автоматическая выдача товаров
autoRestore = 0        # Восстановление активности
autoTicket = 0         # Авто-тикеты (возврат денег за неподтвержденные заказы)
```

---

## 📁 Структура проекта

```
Starvell-cardinal/
├── main.py                 # Точка входа
├── version.py              # Версия приложения
├── requirements.txt        # Зависимости
├── first_setup.py         # Первичная настройка
│
├── api/                    # API клиент для Starvell.com
│   ├── client.py          # Основной клиент
│   ├── session.py         # Управление сессией
│   ├── exceptions.py       # Исключения
│   ├── utils.py           # Утилиты
│   └── config.py          # Конфигурация API
│
├── bot/                    # Основной код бота
│   ├── bot_core.py        # Инициализация бота
│   │
│   ├── core/              # Базовые компоненты
│   │   ├── config.py      # Конфигурация бота
│   │   ├── middlewares.py # Мидлвары (проверка доступа и т.д.)
│   │   ├── storage.py     # База данных и хранилище
│   │   ├── services.py    # Основные сервисы
│   │   ├── notifications.py # Система уведомлений
│   │   └── templates.py     # Шаблоны сообщений
│   │
│   ├── features/          # Функции автоматизации
│   │   ├── auto_delivery.py   # Автоматическая выдача товаров
│   │   ├── auto_raise.py      # Автоматический поднос лотов
│   │   ├── auto_response.py   # Автоответчик
│   │   ├── auto_restore.py    # Восстановление активности лотов
│   │   ├── autoticket.py      # Авто-тикеты
│   │   ├── auto_update.py     # Обновление информации
│   │   ├── blacklist.py       # Черный список пользователей
│   │   ├── keep_alive.py      # Поддержание активности
│   │   └── tasks.py           # Фоновые задачи
│   │
│   ├── handlers/          # Обработчики команд и событий
│   │   ├── handlers.py    # Основные команды (/start, /help и т.д.)
│   │   ├── auto_delivery_handlers.py  # Команды для автовыдачи
│   │   ├── blacklist_handlers.py      # Команды чёрного списка
│   │   ├── custom_commands_handlers.py # Кастомные команды
│   │   ├── extra_handlers.py          # Дополнительные обработчики TODO: переместить в основной хендлер
│   │   ├── plugins_handlers.py        # Команды для работы с плагинами
│   │   └── templates_handlers.py      # Шаблоны сообщений
│   │
│   ├── keyboards/         # Клавиатуры бота
│   │   ├── keyboards.py   # Основные клавиатуры
│   │   └── plugins.py     # Клавиатуры для плагинов
│   │
│   └── plugins/           # Система плагинов
│       ├── manager.py     # Менеджер плагинов
│       └── cp.py          # Панель управления плагинами
│
├── plugins/               # Директория с плагинами
│ 
│
├── storage/               # Хранилище данных
│   └── products/          # Товары для автовыдачи
│
├── configs/               # Конфигурационные файлы
│   └── _main.cfg          # Главная конфигурация (создаётся автоматически)
│
├── docs/                  # Документация
│   └── PLUGINS_API.md     # API для плагинов
│
└── LICENSE                # Лицензия MIT
```

---

## 🎮 Команды бота

### Основные команды

| Команда | Описание |
|---------|---------|
| `/start` | Главное меню |
| `/update` | Обновить информацию |
| `/logs` | Получить логи |
| `/restart` | Перезапустить бота |

### Управление автоматизацией

- **Автодоставка** — управление лотами с автоматической выдачей товаров
- **Чёрный список** — блокировка пользователей
- **Параметры** — настройка функций автоматизации
- **Плагины** — управление установленными плагинами

---

## 🔌 Система плагинов

### Создание плагина

Создайте файл `plugins/my_plugin.py`:

```python
"""
Мой плагин для Starvell Cardinal
"""

# === МЕТАДАННЫЕ ===
PLUGIN_NAME = "Мой плагин"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Описание моего плагина"
PLUGIN_AUTHOR = "Ваше имя"
PLUGIN_UUID = "my-plugin-uuid-12345"

# === ФУНКЦИИ-ОБРАБОТЧИКИ ===
def on_init():
    """Вызывается при загрузке плагина"""
    print(f"✅ {PLUGIN_NAME} загружен!")

async def on_new_message(message_data, *args):
    """Вызывается при получении нового сообщения"""
    print(f"📨 Сообщение от {message_data['author']}: {message_data['content']}")

# === ПРИВЯЗКА К СОБЫТИЯМ ===
BIND_TO_INIT = [on_init]
BIND_TO_NEW_MESSAGE = [on_new_message]
```

### Доступные события

- **`BIND_TO_PRE_INIT`** — перед инициализацией бота
- **`BIND_TO_INIT`** — после инициализации бота
- **`BIND_TO_DELETE`** — при удалении плагина
- **`BIND_TO_NEW_MESSAGE`** — при получении нового сообщения
- **`BIND_TO_NEW_ORDER`** — при получении нового заказа

Полная документация: [PLUGINS_API.md](docs/PLUGINS_API.md)

---

## 📊 Логирование

Бот использует продвинутую систему логирования с цветным выводом:

```
[I] 14:23:45 | Запуск Starvell Cardinal
[D] 14:23:46 | Инициализация компонентов
[W] 14:23:47 | AutoDelivery отключена
[E] 14:23:48 | Ошибка подключения к API
```

Уровни логирования:
- **D** (DEBUG) — Информация для отладки
- **I** (INFO) — Информационные сообщения
- **W** (WARNING) — Предупреждения
- **E** (ERROR) — Ошибки
- **C** (CRITICAL) — Критические ошибки

---

## 🛠️ Разработка

### Добавление новой функции

1. Создайте модуль в `bot/features/` для логики
2. Добавьте обработчики в `bot/handlers/`
3. Создайте клавиатуру в `bot/keyboards/` (при необходимости)
4. Зарегистрируйте в `bot/bot_core.py`

### Запуск с отладкой

```bash
python main.py
# Логи будут выводиться с полной информацией для отладки
```

---

## 🐛 Решение проблем

### Ошибка: "session_cookie не установлена"

1. Откройте `configs/_main.cfg`
2. Установите значение `session_cookie` с вашей сессией Starvell
3. Перезапустите бота

### Ошибка: "Не удалось подключиться к API"

1. Проверьте интернет-соединение
2. Убедитесь, что Starvell.com доступен
3. Обновите User-Agent в конфигурации

---

## 📝 API Starvell

Бот взаимодействует с API Starvell.com для:
- Получения информации о лотах
- Управления товарами
- Обработки заказов
- Отправки сообщений

Основной класс: `api.client.StarvellClient`

---

## 📚 Документация

### Для разработчиков плагинов

- **[Документация API плагинов](docs/PLUGINS_API.md)** — полное руководство по созданию плагинов
- **[API Reference](docs/API_REFERENCE.md)** — справочник методов StarvellService с примерами данных

### Для пользователей

- [Конфигурация бота](bot/core/config.py) — настройка параметров

---

## 🤝 Вклад в проект

Если вы нашли ошибку или хотите предложить улучшение:

Напишите сюда: [Отправить репорт](https://t.me/starvellbugreport_bot).

---

## 📄 Лицензия

Проект распространяется под лицензией **MIT**. См. файл [LICENSE](LICENSE) для подробностей.

---

## 🔗 Ссылки

- **Telegram:** [@embedium](https://t.me/embedium)
- **Telegram:** [@StarvellPlugins](https://t.me/StarvellPlugins)
- **Платформа:** [Starvell.com](https://starvell.com)

---

> Keywords: Telegram bot, Python, aiogram, Starvell, marketplace automation, autodelivery

**Спасибо за использование Starvell Cardinal!** 🚀
