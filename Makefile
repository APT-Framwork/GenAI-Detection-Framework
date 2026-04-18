# STRIX top-level Makefile.
#
# `make help` lists everything. The headline target is `make smoke` which
# proves end-to-end that an alert flows from Redis Streams through the
# full ML pipeline into Postgres + SSE.

.DEFAULT_GOAL := help
SHELL := /bin/bash

COMPOSE        := docker compose -f infra/compose.api.yml
COMPOSE_FULL   := $(COMPOSE) --profile workers --profile queue
COMPOSE_OBS    := $(COMPOSE) --profile obs
ENV_FILE       := apps/api/.env

ADMIN_EMAIL    ?= admin@strix.local
ADMIN_PASSWORD ?= changeme

# Pick up env defaults so make targets inherit DB_PASSWORD etc.
ifneq (,$(wildcard $(ENV_FILE)))
include $(ENV_FILE)
export
endif

# --------------------------------------------------------------------- help

.PHONY: help
help:
	@printf "STRIX targets:\n\n"
	@printf "  \033[1mBring-up\033[0m\n"
	@printf "    \033[36mmake env\033[0m              create apps/api/.env from .env.example if missing\n"
	@printf "    \033[36mmake up\033[0m               start postgres + redis + api + migrate (foreground build)\n"
	@printf "    \033[36mmake up-d\033[0m             same, detached\n"
	@printf "    \033[36mmake workers\033[0m          start the worker profile (normalizer + inference + writer + arq)\n"
	@printf "    \033[36mmake obs\033[0m              start the observability profile (prometheus)\n"
	@printf "    \033[36mmake down\033[0m             stop everything (keep volumes)\n"
	@printf "    \033[36mmake nuke\033[0m             stop + drop volumes (DATA LOSS)\n"
	@printf "\n  \033[1mDay-to-day\033[0m\n"
	@printf "    \033[36mmake migrate\033[0m          run alembic upgrade head\n"
	@printf "    \033[36mmake seed\033[0m             create / rotate the bootstrap admin user\n"
	@printf "    \033[36mmake logs\033[0m             follow logs from every running container\n"
	@printf "    \033[36mmake test\033[0m             run the api unit-test suite\n"
	@printf "    \033[36mmake openapi\033[0m          regenerate apps/web/lib/openapi.json\n"
	@printf "\n  \033[1mEnd-to-end\033[0m\n"
	@printf "    \033[36mmake smoke\033[0m            full pipeline smoke test (alert → DB + SSE)\n"
	@printf "    \033[36mmake smoke-fast\033[0m       same but assumes stack is already up + admin seeded\n"
	@printf "    \033[36mmake smoke-mobile\033[0m     mobile-contract smoke (register → Bearer → SSE → logout)\n"
	@printf "\nEnv vars: ADMIN_EMAIL ADMIN_PASSWORD (defaults: admin@strix.local / changeme)\n"

# --------------------------------------------------------------------- env

.PHONY: env
env:
	@if [ -f "$(ENV_FILE)" ]; then \
		echo "✓ $(ENV_FILE) exists"; \
	else \
		cp apps/api/.env.example $(ENV_FILE); \
		echo "✓ wrote $(ENV_FILE) from .env.example"; \
		echo "  → edit it: at minimum set DB_PASSWORD and AUTH_JWT_SECRET"; \
	fi

# --------------------------------------------------------------------- compose

.PHONY: up up-d workers obs down nuke restart logs ps
up: env
	$(COMPOSE) --env-file $(ENV_FILE) up --build

up-d: env
	$(COMPOSE) --env-file $(ENV_FILE) up -d --build

workers: env
	$(COMPOSE_FULL) --env-file $(ENV_FILE) up -d --build

obs: env
	$(COMPOSE_OBS) --env-file $(ENV_FILE) up -d

down:
	$(COMPOSE) --env-file $(ENV_FILE) down

nuke:
	$(COMPOSE) --env-file $(ENV_FILE) down -v

restart:
	$(COMPOSE) --env-file $(ENV_FILE) restart api

logs:
	$(COMPOSE_FULL) --env-file $(ENV_FILE) logs -f --tail=50

ps:
	$(COMPOSE_FULL) --env-file $(ENV_FILE) ps

# --------------------------------------------------------------------- ops

.PHONY: migrate seed test openapi
migrate:
	$(COMPOSE) --env-file $(ENV_FILE) run --rm migrate

seed:
	$(COMPOSE) --env-file $(ENV_FILE) exec -T api \
		python /app/infra/scripts/seed_admin.py \
		--email "$(ADMIN_EMAIL)" \
		--password "$(ADMIN_PASSWORD)" \
		--role admin

test:
	cd apps/api && DB_PASSWORD=test python -m pytest tests/unit -q

openapi:
	DB_PASSWORD=test python infra/scripts/dump_openapi.py apps/web/lib/openapi.json

# --------------------------------------------------------------------- smoke

.PHONY: smoke smoke-fast smoke-mobile
smoke: env
	@echo "▶ make smoke — bringing the full stack up first"
	$(COMPOSE_FULL) --env-file $(ENV_FILE) up -d --build
	@echo "▶ waiting for api /health …"
	@for i in $$(seq 1 30); do \
		curl -fsS http://localhost:8000/health > /dev/null 2>&1 && break; \
		printf "."; sleep 1; \
	done
	@echo
	@$(MAKE) seed ADMIN_EMAIL="$(ADMIN_EMAIL)" ADMIN_PASSWORD="$(ADMIN_PASSWORD)"
	@$(MAKE) smoke-fast

smoke-fast:
	python infra/scripts/smoke.py \
		--api http://localhost:8000 \
		--redis redis://localhost:6379/0 \
		--admin-email "$(ADMIN_EMAIL)" \
		--admin-password "$(ADMIN_PASSWORD)" \
		--timeout 90

# Mobile-contract smoke — doesn't need the worker profile, just the api.
# Validates: register (mobile path) · body-refresh · device register /
# list / unregister · Bearer on dashboard + alerts · SSE handshake · logout.
smoke-mobile:
	python infra/scripts/smoke_mobile.py \
		--api http://localhost:8000 \
		--timeout 15
