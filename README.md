<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=28&duration=3000&pause=800&color=C41E3A&center=true&vCenter=true&width=520&lines=Starvell+Cardinal;Automation+for+Starvell.com;Plugins+%C2%B7+Logs+%C2%B7+API" alt="Typing SVG" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Cardinal-v0.3.7-C41E3A?style=flat-square&labelColor=1a0a0d" />
  <img src="https://img.shields.io/badge/Python-3.8+-FFD700?style=flat-square&labelColor=1a0a0d&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-2d1b1f?style=flat-square&labelColor=1a0a0d" />
  <img src="https://img.shields.io/badge/License-MIT-8B0000?style=flat-square&labelColor=1a0a0d" />
</p>

<p align="center">
  <a href="https://t.me/starvellingbot"><img src="https://img.shields.io/badge/Канал-@starvellingbot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" /></a>
  <a href="https://t.me/knowtake"><img src="https://img.shields.io/badge/Автор-@knowtake-C41E3A?style=for-the-badge&logo=telegram&logoColor=white" /></a>
  <a href="https://starvell.com"><img src="https://img.shields.io/badge/Starvell-marketplace-0f3460?style=for-the-badge" /></a>
</p>

<br>

```text
      ╭──────────────────────────────────────────────────────────╮
      │  ♜  CARDINAL · headless Starvell automation engine       │
      │                                                          │
      │   poll chats ──► plugins ──► orders ──► bump ──► logs   │
      ╰──────────────────────────────────────────────────────────╯
```

> **Starvell Cardinal** — Telegram-панель управления для продавцов [Starvell.com](https://starvell.com).  
> Читает ЛС покупателей, гоняет плагины, поднимает лоты — уведомления в **логах**, не в спаме TG.

<br>

<table>
<tr>
<td width="33%" align="center">

### 📡 Inbox
FunPay-style **chat listener**  
`lastMessage` API · plugin events

</td>
<td width="33%" align="center">

### 🧩 Plugins
`BIND_TO_NEW_MESSAGE`  
`BIND_TO_NEW_ORDER` · hooks

</td>
<td width="33%" align="center">

### 🛡️ Anti-bot
Next.js fallback · rate limit  
HTTP keep-alive

</td>
</tr>
</table>

<br>

## ⚡ Установка

```bash
wget https://raw.githubusercontent.com/etheriumflipper/StarvellCardinal/main/install.sh -O install.sh && bash install.sh
```

<details>
<summary><b>🐧 Linux / VPS</b></summary>

```bash
git clone https://github.com/etheriumflipper/StarvellCardinal.git
cd StarvellCardinal
sudo bash install.sh
sudo systemctl enable --now starvell-cardinal
sudo journalctl -u starvell-cardinal -f    # логи в реальном времени
```

</details>

<details>
<summary><b>🪟 Windows</b></summary>

```bat
git clone https://github.com/etheriumflipper/StarvellCardinal.git
cd StarvellCardinal
Setup.bat
Start.bat
```

</details>

<br>

## 🎛️ Модули

| | Модуль | Что делает |
|:---:|:---|:---|
| ⤴️ | **Auto-raise** | Поднятие лотов по категориям (fallback через заказы, если профиль 403) |
| 💬 | **Chat listener** | Ловит ЛС покупателей — даже когда Starvell отдаёт только `lastMessage` |
| 🎁 | **Auto-delivery** | Выдача товаров по шаблонам |
| 🤖 | **Auto-response** | Ответы на новые заказы |
| 🟢 | **Keep-alive** | Вечный онлайн (HTTP heartbeat, Socket.IO fallback) |
| 🧩 | **Plugins** | Python-модули в `plugins/` — [документация](docs/PLUGINS_API.md) |
| 🔄 | **Auto-update** | `/update` с GitHub Releases |

<br>

## 🧩 Плагины за 60 секунд

```python
# plugins/hello.py
NAME, VERSION, DESCRIPTION, AUTHOR = "Hello", "1.0.0", "Test", "@knowtake"
UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

async def on_new_message(data, starvell_service=None, **kwargs):
  if data.get("content", "").lower() == "привет":
    await starvell_service.send_message(data["chat_id"], "Привет! Cardinal на связи.")

BIND_TO_NEW_MESSAGE = [on_new_message]
```

Положи файл в `plugins/` → `systemctl restart starvell-cardinal` → пиши в ЛС на Starvell → смотри `journalctl -f`.

📚 [API Reference](docs/API_REFERENCE.md) · [Plugins API](docs/PLUGINS_API.md)

<br>

## 📋 Логи вместо TG-спама

По умолчанию **уведомления только в journal**, Telegram не засоряется:

```ini
# configs/_main.cfg
[Notifications]
newMessages = 0
newOrders = 0
```

Включить TG обратно: `/notifications` в боте или `newMessages = 1`.

<br>

## 🗂️ Структура

```text
StarvellCardinal/
├── main.py
├── api/              # Starvell client (Next.js + REST)
├── bot/
│   ├── core/         # chat_listener, notifications, services
│   ├── features/     # auto_raise, keep_alive, tasks
│   └── plugins/      # plugin manager
├── configs/_main.cfg
├── docs/             # API_REFERENCE · PLUGINS_API
└── plugins/          # твои .py модули
```

<br>

## 📦 Changelog (recent)

| Ver | Highlights |
|:---:|:---|
| **0.3.7** | TG-уведомления off по умолчанию · только логи |
| **0.3.6** | Fix `lastMessage` DM detection · unread on startup |
| **0.3.5** | FunPay-style chat events для плагинов |
| **0.3.4** | Auto-raise 403 fallback chain |
| **0.3.0** | Anti-bot · rebrand @knowtake |

<br>

## 🔧 Первый запуск

1. **Bot Token** — `@BotFather`
2. **Пароль** — для входа в панель бота
3. **session_cookie** — из браузера на starvell.com

Мастер `first_setup.py` создаст конфиг и systemd-сервис.

<br>

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=soft&color=C41E3A:1a0a0d&height=120&section=footer&text=♜%20Starvell%20Cardinal%20·%20@knowtake&fontSize=22&fontColor=FFD700" width="90%" />
</p>

<p align="center">
  <sub>MIT © <a href="https://t.me/knowtake">@knowtake</a> · <a href="https://t.me/starvellingbot">@starvellingbot</a></sub>
</p>
