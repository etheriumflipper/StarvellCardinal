# 📚 API Reference - Краткий справочник

## StarvellService Methods

### Методы для работы с сообщениями

#### `send_message(chat_id: str, content: str) -> dict`

Отправить сообщение в чат заказа.

**Параметры:**
- `chat_id` (str): UUID чата
- `content` (str): Текст сообщения

**Возвращает:**
```python
{
    "success": True,  # или False при ошибке
    # Дополнительные поля от API Starvell
}
```

**Пример:**
```python
await starvell_service.send_message(
    "019b8386-1e8f-f31d-9e66-b05331f70af6",
    "Здравствуйте! Ваш заказ принят."
)
```

---

### Методы для работы с заказами

#### `get_order_details(order_id: str) -> dict`

Получить полную информацию о заказе.

**Параметры:**
- `order_id` (str): UUID заказа

**Возвращает:**
```python
{
    "pageProps": {
        "order": {
            "id": "019b97fa-497b-3dd2-a041-da54f9378d8e",
            "status": "CREATED",              # CREATED, COMPLETED, CANCELED, etc.
            "basePrice": 100,                  # Цена в копейках
            "totalPrice": 108,                 # Итого с комиссией (копейки)
            "buyerId": 1111,                 # ID покупателя (число)
            "sellerId": 2222,                  # ID продавца (число)
            "offerId": 141378,                 # ID лота
            "quantity": 1000,                  # Количество единиц товара
            "createdAt": "2026-01-07T10:22:01.068Z",
            "updatedAt": "2026-01-07T10:22:01.068Z",
            "refundedAt": None,
            "completedAt": None,
            "buyer": {
                "id": 1111,
                "username": "Hackep",
                "isOnline": True,
                "lastOnlineAt": "2026-01-07T09:59:52.022Z",
                "createdAt": "2026-01-03T11:00:58.690Z",
                "avatar": "uuid",
                "banner": None,
                "description": None,
                "isKycVerified": False,
                "isBanned": False,
                "isSellingEnabled": True,
                "roles": [],
                "rating": 0,
                "reviewsCount": 0
            },
            "seller": {
                "id": 2222,
                "username": "Kirito",
                "isOnline": True,
                # ... аналогично buyer
            },
            "offerDetails": {
                "game": {
                    "id": 14,
                    "name": "Telegram",
                    "slug": "telegram"
                },
                "type": "LOT",
                "images": [],
                "category": {
                    "id": 175,
                    "name": "Услуги",
                    "slug": "services"
                },
                "subCategory": {
                    "id": 633,
                    "name": "Просмотры"
                },
                "availability": 999991999,
                "deliveryTime": {
                    "to": {"unit": "MINUTES", "value": 15},
                    "from": {"unit": "MINUTES", "value": 1}
                },
                "descriptions": {
                    "rus": {
                        "description": "Полное описание товара...",
                        "briefDescription": "Краткое описание"
                    }
                },
                "instantDelivery": False
            },
            "orderArgs": [],
            "reviewVisibleAfterRefund": False
        },
        "chat": {
            "id": "019b8386-1e8f-f31d-9e66-b05331f70af6",  # ⚠️ UUID чата здесь!
            # ... другие поля чата
        },
        "review": None,  # или объект отзыва если есть
        "messages": [
            # Массив сообщений в чате
        ],
        "user": {...},  # Информация о текущем пользователе
        "timeZone": "Europe/Moscow",
        "sid": "session-id",
        "currentTheme": "dark"
    },
    "__N_SSP": True
}
```

**Важно:**
- `chat.id` (UUID чата) находится в `pageProps.chat.id`
- `buyerId` (ID покупателя) находится в `pageProps.order.buyerId`
- Цены указаны в **копейках**: `basePrice / 100` = рубли

**Пример:**
```python
details = await starvell_service.get_order_details(order_id)
page_props = details["pageProps"]
order_info = page_props["order"]
chat_data = page_props["chat"]

# Получить данные
chat_id = chat_data["id"]              # UUID чата
buyer_id = order_info["buyerId"]       # ID покупателя (число)
quantity = order_info["quantity"]      # Количество
price_rub = order_info["totalPrice"] / 100  # Цена в рублях
```

---

#### `get_orders() -> list[dict]`

Получить список всех заказов.

**Возвращает:**
```python
[
    {
        "id": "order-uuid-1",
        "status": "CREATED",
        "totalPrice": 108,
        "buyer": {...},
        "seller": {...},
        # ... остальные поля как в get_order_details
    },
    {
        "id": "order-uuid-2",
        # ...
    }
]
```

**Пример:**
```python
orders = await starvell_service.get_orders()
for order in orders:
    if order["status"] == "CREATED":
        print(f"Новый заказ: {order['id']}")
```

---

#### `refund_order(order_id: str) -> dict`

Вернуть деньги за заказ (отменить заказ).

**Параметры:**
- `order_id` (str): UUID заказа

**Возвращает:**
```python
{
    "success": True,  # или False при ошибке
    # Дополнительные поля от API
}
```

**Пример:**
```python
result = await starvell_service.refund_order(order_id)
if result.get("success"):
    print("Заказ успешно отменён")
```

---

### Методы для работы с пользователями

#### `find_chat_by_user_id(user_id: str) -> str | None`

Найти UUID чата с конкретным пользователем.

**Параметры:**
- `user_id` (str): ID пользователя (buyerId как строка)

**Возвращает:**
- `str`: UUID чата
- `None`: Чат не найден

**Пример:**
```python
# Найти чат с покупателем
buyer_id = "142989"
chat_id = await starvell_service.find_chat_by_user_id(buyer_id)

if chat_id:
    await starvell_service.send_message(chat_id, "Привет!")
else:
    print("Чат не найден")
```

---

#### `send_message_by_user_id(user_id: str, content: str) -> dict`

Отправить сообщение пользователю по ID (ищет существующий чат).

```python
await starvell_service.send_message_by_user_id("142989", "Привет!")
```

---

#### `get_chat_messages(chat_id: str, limit: int = 50) -> list[dict]`

Загрузить историю сообщений чата (с подгрузкой полной страницы `/chat/{id}`).

```python
messages = await starvell_service.get_chat_messages(chat_id, limit=30)
```

---

## Структуры данных событий

### order_data (BIND_TO_NEW_ORDER)

Данные, передаваемые в обработчик `on_new_order`:

```python
{
    'id': str,                    # UUID заказа
    'buyer': str,                 # Имя покупателя
    'amount': float,              # Сумма в рублях (уже конвертирована)
    'lot_name': str,              # Название лота
    'lot_description': str,       # Описание лота
    'status': str,                # Статус: CREATED, COMPLETED, etc.
    'chat_id': str                # UUID чата (пусто если не найден)
}
```

**Пример:**
```python
{
    'id': '019b97fa-497b-3dd2-a041-da54f9378d8e',
    'buyer': 'Hackep',
    'amount': 1.08,
    'lot_name': 'АВТОНАКРУТКА ПРОСМОТРОВ TELEGRAM',
    'lot_description': '💜 Минимальный заказ: 50\nID:5001\n#Quan:1',
    'status': 'CREATED',
    'chat_id': '019b8386-1e8f-f31d-9e66-b05331f70af6'
}
```

---

### message_data (BIND_TO_NEW_MESSAGE)

Данные, передаваемые в обработчик `on_new_message`:

```python
{
    'chat_id': str,       # UUID чата
    'author': str,        # ID автора (buyerId как строка)
    'content': str,       # Текст сообщения
    'message_id': str     # UUID сообщения
}
```

**Пример:**
```python
{
    'chat_id': '019b8386-1e8f-f31d-9e66-b05331f70af6',
    'author': '142989',
    'content': 'https://t.me/channel/123',
    'message_id': '019b9803-0ef6-eb89-eb81-0e72b7c2ff42'
}
```

**⚠️ Важно:**
- `author` содержит **ID покупателя** (число как строка), а не имя!
- Чтобы получить имя, используйте `get_order_details()` и найдите `buyer.username`

---

## Частые задачи

### Отправить сообщение при новом заказе

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    if not starvell_service or not order_data.get('chat_id'):
        return
    
    await starvell_service.send_message(
        order_data['chat_id'],
        f"👋 Здравствуйте!\n\n"
        f"📦 Заказ: {order_data['lot_name']}\n"
        f"💰 Сумма: {order_data['amount']}₽"
    )
```

### Получить количество товара из заказа

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    if not starvell_service:
        return
    
    # Получить полные детали
    details = await starvell_service.get_order_details(order_data['id'])
    quantity = details["pageProps"]["order"]["quantity"]
    
    print(f"Заказано единиц: {quantity}")
```

### Найти заказ по сообщению от покупателя

```python
async def on_new_message(message_data: dict, starvell_service=None, **kwargs):
    # author - это buyerId покупателя
    buyer_id = message_data['author']
    
    # Найти заказ где buyerId совпадает
    # (нужно хранить соответствие в своих данных плагина)
```

### Извлечь chat_id если его нет в order_data

```python
async def on_new_order(order_data: dict, starvell_service=None, **kwargs):
    chat_id = order_data.get('chat_id')
    
    if not chat_id and starvell_service:
        # Получить из деталей
        details = await starvell_service.get_order_details(order_data['id'])
        page_props = details.get("pageProps", {})
        chat_data = page_props.get("chat", {})
        chat_id = chat_data.get("id")
    
    if chat_id:
        await starvell_service.send_message(chat_id, "Привет!")
```

---

## Типы статусов заказа

| Статус | Описание |
|--------|----------|
| `CREATED` | Заказ создан, ожидает выполнения |
| `COMPLETED` | Заказ выполнен |
| `CANCELED` | Заказ отменён |
| `REFUNDED` | Возврат средств выполнен |

---

## Единицы измерения

### Цены
- API возвращает цены в **копейках**
- `order_data['amount']` уже в **рублях** (конвертировано автоматически)
- `details["pageProps"]["order"]["totalPrice"]` в **копейках** (делить на 100)

### Время
- Все временные метки в формате **ISO 8601**: `"2026-01-07T10:22:01.068Z"`
- Часовой пояс UTC

### ID
- Заказы, чаты, сообщения: **UUID** (строка)
- Пользователи, лоты: **число** (но может быть в виде строки)

---

## Обработка ошибок

Все методы могут выбросить исключения. Всегда оборачивайте в try/except:

```python
try:
    await starvell_service.send_message(chat_id, "Текст")
except Exception as e:
    logger.error(f"Ошибка отправки сообщения: {e}")
```

---

**Обновлено:** 7 января 2026  
**Версия:** Starvell Cardinal 0.0.8
