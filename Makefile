# Объясни! — команды сборки, миграций и деплоя.
# Локальная разработка: docker-compose.yml
# Прод: docker-compose.yml + docker-compose.prod.yml

DC        := docker compose
DC_PROD   := docker compose -f docker-compose.yml -f docker-compose.prod.yml
DC_BOOT   := docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.bootstrap.yml

# Загружаем DOMAIN/EMAIL из .env для команд certbot.
-include .env
export

.PHONY: help
help:
	@echo "Локально:"
	@echo "  make build         — собрать образ"
	@echo "  make up            — поднять db+redis+web+bot+nginx (с миграцией)"
	@echo "  make migrate       — применить миграции (пересборка образа обязательна!)"
	@echo "  make logs          — логи web+bot"
	@echo "  make down          — остановить (данные сохраняются)"
	@echo "  make reset         — остановить и УДАЛИТЬ данные БД (down -v)"
	@echo "  make revision m=.. — сгенерировать новую миграцию (autogenerate)"
	@echo ""
	@echo "Прод (на сервере):"
	@echo "  make prod-build    — собрать образ на сервере"
	@echo "  make prod-migrate  — применить миграции"
	@echo "  make prod-up       — поднять весь стек (TLS)"
	@echo "  make prod-down     — остановить прод-стек"
	@echo "  make cert-init     — первичный выпуск TLS-сертификата (нужны DOMAIN, EMAIL в .env)"
	@echo "  make cert-renew    — продлить сертификат и перечитать nginx"

# ---------- Локально ----------
.PHONY: build up migrate logs down reset revision
build:
	$(DC) build

up: build
	$(DC) up -d

# ВАЖНО: docker compose run НЕ пересобирает образ. Всегда build перед migrate,
# иначе применится старый/пустой набор миграций.
migrate: build
	$(DC) up -d db redis
	$(DC) run --rm migrate

logs:
	$(DC) logs -f web bot

down:
	$(DC) down

reset:
	$(DC) down -v

revision: build
	$(DC) up -d db redis
	$(DC) run --rm -v "$(PWD)/alembic/versions:/code/alembic/versions" web \
		alembic revision --autogenerate -m "$(m)"

# ---------- Прод ----------
.PHONY: prod-build prod-migrate prod-up prod-down cert-init cert-renew
prod-build:
	$(DC_PROD) build

prod-migrate: prod-build
	$(DC_PROD) up -d db redis
	$(DC_PROD) run --rm migrate

prod-up: prod-build prod-migrate
	$(DC_PROD) up -d

prod-down:
	$(DC_PROD) down

# Первичный выпуск: поднимаем nginx в bootstrap-режиме (только HTTP),
# затем certbot certonly через webroot, потом обычный prod-up с TLS.
cert-init:
	$(DC_BOOT) up -d nginx
	$(DC_PROD) run --rm --entrypoint certbot certbot \
		certonly --webroot -w /var/www/certbot \
		-d $(DOMAIN) --email $(EMAIL) --agree-tos --no-eff-email --non-interactive
	$(DC_BOOT) down
	$(DC_PROD) up -d

cert-renew:
	$(DC_PROD) run --rm --entrypoint certbot certbot renew
	$(DC_PROD) exec nginx nginx -s reload
