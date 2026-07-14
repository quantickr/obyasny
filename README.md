# Объясни!

Платформа взаимопомощи студентов: находишь того, кто объяснит нужную тему, а взамен
объясняешь свою тему или платишь «шоколадками» (виртуальная валюта благодарности).
Единый профиль на **сайте** и в **Telegram-боте**, общая база, чат в реальном времени.

## Возможности

- **Поиск + заявки**: находишь пользователя по теме, отправляешь заявку на обмен/шоколадки.
- **Доска объявлений**: публикуешь «учу X ↔ хочу Y», другие откликаются.
- **Авто-подбор пар**: система находит взаимовыгодные пары (я учу тебя A, ты меня B).
- **Чат**: реалтайм на сайте (WebSocket) и в Telegram; сообщения синхронизируются.
- **Шоколадки**: счётчик благодарности, журнал транзакций.
- **Auth**: email+пароль **или** Telegram Login; аккаунты связываются одноразовым кодом.

## Стек

FastAPI (async) · SQLAlchemy 2.0 async · asyncpg · Alembic · aiogram 3 ·
Jinja2 + Tailwind (CDN) · WebSocket + Redis Pub/Sub · Nginx · Docker Compose.

Ключевой принцип: `app/core`, `app/models`, `app/services`, `app/events` — общее ядро;
`app/web` и `app/bot` — тонкие адаптеры. Web и bot запускаются из одного Docker-образа
разными командами.

## Структура

```
app/
  core/       config, database, redis_client, security, logging
  models/     user, topic, listing, request, match, chat, chocolate
  services/   бизнес-логика (не знает про UI)
  events/     шина Redis Pub/Sub для чата
  web/        FastAPI: routers, templates, static, ws_manager
  bot/        aiogram: handlers, middlewares, notifier
alembic/      миграции
nginx/        конфиги (dev / prod / bootstrap)
docker-compose.yml            локальная разработка
docker-compose.prod.yml       прод-override (TLS, restart: always)
docker-compose.bootstrap.yml  только для первичного выпуска сертификата
Makefile                      удобные команды
```

## Локальный запуск

Требуется Docker (с плагином `docker compose`).

```bash
cp .env.example .env
# отредактируйте .env: JWT_SECRET (openssl rand -hex 32), BOT_TOKEN, BOT_USERNAME
make up          # соберёт образ, поднимет db+redis+migrate+web+bot+nginx
make logs        # логи web и bot
```

Сайт: http://localhost (через nginx) или http://localhost:8000 (напрямую web).

Полезное:

```bash
make migrate     # применить миграции (с обязательной пересборкой образа)
make down        # остановить, данные сохранить
make reset       # остановить и УДАЛИТЬ данные БД
make revision m="add something"   # сгенерировать новую миграцию
```

> **Важно про миграции.** `docker compose run` **не** пересобирает образ. Файлы миграций
> копируются в образ на этапе `COPY . .`, поэтому после добавления новой миграции нужно
> `docker compose build` (в `make migrate` это уже учтено). Иначе `alembic upgrade head`
> запустится на устаревшем образе и таблицы не создадутся.

### Telegram-бот локально

1. Получите токен у [@BotFather](https://t.me/BotFather), впишите в `.env`:
   `BOT_TOKEN=...` и `BOT_USERNAME=<username_без_@>`.
2. `make up` — бот запустится в режиме long polling.
3. На сайте в профиле нажмите «Привязать Telegram» → получите ссылку
   `t.me/<bot>?start=<код>` → бот привяжет ваш аккаунт (код живёт 10 мин в Redis).

## Деплой на Timeweb Cloud (VPS по SSH)

Предполагается облачный сервер (VPS) с Ubuntu и доступом по SSH-ключу.

> Аккаунт, платёжные данные, SSH-ключи на сервер добавляет владелец — не автоматизируется.

### 1. Подключение и Docker

```bash
ssh user@SERVER_IP
# Установка Docker, если ещё не стоит:
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # перелогиниться после этого
```

### 2. Доставка кода

```bash
git clone <repo_url> connectstudents && cd connectstudents
# или scp -r ./connectstudents user@SERVER_IP:~/
```

### 3. Настройка .env (прод)

```bash
cp .env.example .env
nano .env
```

Обязательно поменяйте:

- `POSTGRES_PASSWORD` — надёжный пароль; и синхронно в `DATABASE_URL`.
- `JWT_SECRET` — `openssl rand -hex 32`.
- `BOT_TOKEN`, `BOT_USERNAME` — от @BotFather.
- `WEBAPP_BASE_URL=https://ваш-домен` — для ссылок и Telegram Login.
- `DOMAIN=ваш-домен`, `EMAIL=почта@для.letsencrypt`.

> Опционально можно использовать **managed PostgreSQL** от Timeweb: тогда уберите сервис
> `db` из compose и укажите `DATABASE_URL` на managed-инстанс.

### 4. DNS и первичный TLS-сертификат

1. Направьте A-запись домена на IP сервера.
2. Откройте порты 80 и 443 (в панели Timeweb / firewall).
3. Выпустите сертификат (поднимет nginx на HTTP, пройдёт ACME-challenge, включит TLS):

```bash
make cert-init
```

### 5. Запуск стека

```bash
make prod-up
```

Поднимутся db, redis, migrate (применит схему), web, bot, nginx (TLS).
Проверка: откройте `https://ваш-домен`.

### 6. Продление сертификата

Let's Encrypt действует 90 дней. Добавьте в cron (например, раз в неделю):

```bash
0 3 * * 1 cd ~/connectstudents && make cert-renew >> ~/certbot.log 2>&1
```

### Обновление версии на проде

```bash
git pull
make prod-up     # пересоберёт образ, применит новые миграции, перезапустит
```

## Проверка end-to-end

1. Регистрация на сайте (email+пароль).
2. Профиль → добавить темы «умею» и «хочу».
3. Привязать Telegram кодом из профиля.
4. Найти пользователя (поиск / доска / авто-подбор), отправить заявку.
5. Принять заявку → создаётся чат.
6. Написать сообщение на сайте → проверить приход в Telegram и обратно.
7. Начислить «шоколадку» за помощь.
