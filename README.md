<div align="center">

# ✨ Starvell Cardinal

<p>
  <a href="https://t.me/StarvellCardinal">📢 Канал</a> •
  <a href="https://t.me/StarvellPlugins">🧩 Плагины</a> •
  <a href="https://t.me/embedium">👤 Автор</a> •
  <a href="https://github.com/etheriumflipper/StarvellCardinal">💻 GitHub</a>
</p>

<p>
  <img src="https://img.shields.io/badge/Starvell-Automation-1f6feb?style=for-the-badge" alt="Starvell Automation" />
  <img src="https://img.shields.io/badge/Telegram-Bot-2ea44f?style=for-the-badge" alt="Telegram Bot" />
  <img src="https://img.shields.io/badge/Linux-Systemd-f2cc60?style=for-the-badge" alt="Linux Systemd" />
</p>

<h3>Starvell Cardinal — Telegram-бот для автоматизации работы со Starvell</h3>

<p>⚙️ Чистый Cardinal • 🔄 Автообновления • 🧩 Система плагинов • 🛠️ Установка одной командой</p>

</div>

> Starvell Cardinal — это Telegram-бот для автоматизации работы со Starvell. Starvell Cardinal помогает управлять заказами, лотами, уведомлениями, плагинами и обновлениями из одной панели.

Starvell Cardinal создан для продавцов, которым нужен удобный Telegram-интерфейс вокруг Starvell. Проект делает упор на быструю установку, автоматическую обработку заказов, поддержку плагинов, обновления через GitHub и запуск на Linux-хостинге через `systemd`.

Если вы ищете `Starvell Cardinal`, это основной публичный GitHub-репозиторий проекта с актуальным установщиком, исходным кодом, релизами и системой автообновлений.

Быстрые ссылки:

- GitHub: https://github.com/etheriumflipper/StarvellCardinal
- Telegram-канал: https://t.me/StarvellCardinal
- Telegram-плагины: https://t.me/StarvellPlugins
- Автор: https://t.me/embedium

## ⚡ Установка одной командой

```bash
wget https://raw.githubusercontent.com/etheriumflipper/StarvellCardinal/main/install.sh -O install.sh && bash install.sh
```

## 🚀 Быстрый старт

### 🐧 Linux / VPS

Установка одной командой:

```bash
wget https://raw.githubusercontent.com/etheriumflipper/StarvellCardinal/main/install.sh -O install.sh && bash install.sh
```

Управление сервисом после установки:

```bash
sudo systemctl status starvell-cardinal
sudo systemctl restart starvell-cardinal
sudo systemctl stop starvell-cardinal
sudo journalctl -u starvell-cardinal -f
```

### 🪟 Windows

```bash
git clone https://github.com/etheriumflipper/StarvellCardinal.git
cd StarvellCardinal
Setup.bat
Start.bat
```

## 🧠 Что умеет Starvell Cardinal

- ⚙️ Автоматизировать работу со `Starvell.com`
- 📦 Управлять лотами и товарами
- 📨 Отслеживать заказы и сообщения
- 🔔 Отправлять уведомления в Telegram
- 🛠️ Проводить первичную настройку через мастер
- 🔄 Проверять обновления и уведомлять о новых версиях
- 🧩 Поддерживать отдельную систему плагинов

## 🔄 Автообновления

Starvell Cardinal умеет проверять обновления при запуске и в фоне.

Когда в репозитории выходит новая версия:

- 👀 бот видит новую `VERSION`
- 📨 администраторам приходит уведомление в Telegram
- 🏷️ в сообщении показывается текущая и новая версия
- 🔘 доступна кнопка `Обновить сейчас`
- ⌨️ также можно использовать команду `/update`

Важно: чтобы обновление обнаружилось, перед публикацией новой версии нужно повышать `VERSION` в [version.py](version.py).

## 📥 Установка из репозитория

Если хотите установить вручную:

```bash
git clone https://github.com/etheriumflipper/StarvellCardinal.git
cd StarvellCardinal
sudo bash install.sh
```

Установщик:

- 📦 ставит зависимости
- 🐍 создает виртуальное окружение
- 🧭 запускает `first_setup.py`
- 🔌 создает `systemd`-сервис
- 🟢 поднимает бота в автономном режиме

## 🧷 Первый запуск

Во время настройки бот попросит:

1. `Bot Token` от `@BotFather`
2. пароль для доступа к боту
3. `session_cookie` от `Starvell.com`

После завершения мастер создает `configs/_main.cfg`, а сервис запускается автоматически.

## 🗂️ Структура проекта

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

`plugins/` в публичной версии остается пустой, чтобы вы могли развернуть чистый Cardinal и добавлять нужные плагины отдельно.

## 🛠️ Разработка

- 🧠 Логика бота: `bot/`
- 🌐 API-интеграция: `api/`
- 🧩 Система плагинов: `bot/plugins/` и `plugins/`
- 📘 Документация по плагинам: [docs/PLUGINS_API.md](docs/PLUGINS_API.md)

## 🔗 Ссылки

- 👤 Автор: [@embedium](https://t.me/embedium)
- 📢 Telegram-канал: [@StarvellCardinal](https://t.me/StarvellCardinal)
- 🧩 Плагины: [@StarvellPlugins](https://t.me/StarvellPlugins)
- 💻 GitHub: [etheriumflipper/StarvellCardinal](https://github.com/etheriumflipper/StarvellCardinal)
- 🌍 Платформа: [Starvell.com](https://starvell.com)

## 📄 Лицензия

Проект распространяется по лицензии [MIT](LICENSE).
