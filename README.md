# ✨ Starvell Cardinal ✨

> 🚀 Telegram-бот для автоматизации `Starvell.com`

> 🔥 Чистый Cardinal • ⚙️ Автонастройка • 🔄 Автообновления • 🧩 Плагины

## 🌐 Links

- 👤 Author: [@embedium](https://t.me/embedium)
- 📢 Channel: [@StarvellCardinal](https://t.me/StarvellCardinal)
- 🧩 Plugins: [@StarvellPlugins](https://t.me/StarvellPlugins)
- 💻 GitHub: [etheriumflipper/StarvellCardinal](https://github.com/etheriumflipper/StarvellCardinal)

## ⚡ One Command Install

```bash
wget https://raw.githubusercontent.com/etheriumflipper/StarvellCardinal/main/install.sh -O install.sh && bash install.sh
```

Starvell Cardinal помогает держать магазин под контролем: отслеживать заказы, управлять лотами, настраивать автодействия и получать уведомления в Telegram.

## Быстрый старт

### Linux / VPS

Установка одной командой:

```bash
wget https://raw.githubusercontent.com/etheriumflipper/StarvellCardinal/main/install.sh -O install.sh && bash install.sh
```

После установки управление сервисом:

```bash
sudo systemctl status starvell-cardinal
sudo systemctl restart starvell-cardinal
sudo systemctl stop starvell-cardinal
sudo journalctl -u starvell-cardinal -f
```

### Windows

```bash
git clone https://github.com/etheriumflipper/StarvellCardinal.git
cd StarvellCardinal
Setup.bat
Start.bat
```

## Что умеет бот

- Автоматизация работы со `Starvell.com`
- Управление лотами и товарами
- Отслеживание заказов и сообщений
- Telegram-уведомления по событиям
- Первичная настройка через мастер
- Автообновление с уведомлением о новой версии
- Поддержка собственной системы плагинов

## Автообновление

Starvell Cardinal умеет проверять обновления при запуске и в фоне.

Если в репозитории выходит новая версия:

- бот видит новую `VERSION`
- админам приходит уведомление в Telegram
- в сообщении показывается текущая и новая версия
- доступна кнопка `Обновить сейчас`
- также можно использовать команду `/update`

Важно: чтобы обновление обнаружилось, при публикации новой версии нужно менять значение `VERSION` в [version.py](version.py).

## Установка из репозитория

Если хотите ставить вручную:

```bash
git clone https://github.com/etheriumflipper/StarvellCardinal.git
cd StarvellCardinal
sudo bash install.sh
```

Установщик:

- ставит зависимости
- создает виртуальное окружение
- запускает `first_setup.py`
- создает `systemd`-сервис
- поднимает бота в автономном режиме

## Первый запуск

Во время настройки бот попросит:

1. `Bot Token` от `@BotFather`
2. пароль для входа в панель бота
3. `session_cookie` от `Starvell.com`

После завершения мастер создает `configs/_main.cfg`, а сервис запускается автоматически.

## Структура проекта

```text
StarvellCardinal/
├── main.py
├── first_setup.py
├── version.py
├── install.sh
├── start.sh
├── api/
├── bot/
├── configs/
├── docs/
├── plugins/
└── storage/
```

`plugins/` в публичной версии оставлен пустым, чтобы вы могли разворачивать свой чистый Cardinal и добавлять нужные плагины отдельно.

## Разработка и кастомизация

- Основная логика бота: `bot/`
- Работа с API: `api/`
- Система плагинов: `bot/plugins/` и `plugins/`
- Документация по плагинам: [docs/PLUGINS_API.md](docs/PLUGINS_API.md)

## Ссылки

- Автор: [@embedium](https://t.me/embedium)
- Telegram-канал: [@StarvellCardinal](https://t.me/StarvellCardinal)
- Плагины: [@StarvellPlugins](https://t.me/StarvellPlugins)
- GitHub: [etheriumflipper/StarvellCardinal](https://github.com/etheriumflipper/StarvellCardinal)
- Платформа: [Starvell.com](https://starvell.com)

## Лицензия

Проект распространяется по лицензии [MIT](LICENSE).
