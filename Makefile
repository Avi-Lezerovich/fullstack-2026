# =============================================================================
#  LolSuit - shortcuts for the things you do more than once
# =============================================================================
#  `make help` lists everything. The real logic lives in prod/release.sh and
#  prod/deploy.sh - this file is a memorable front door, not a second
#  implementation. Anything non-trivial here would be logic you cannot test and
#  cannot run without make installed.
# =============================================================================

# Tabs matter in make; every recipe line below is indented with a real tab.
.DEFAULT_GOAL := help
SHELL := /bin/bash

COMPOSE      := docker compose
PROD_COMPOSE := docker compose -f prod/docker-compose.yml

# `make release VERSION=v1.0.1` or `make release v1.0.1` both read naturally;
# support the first, which is the one that cannot be mistaken for a target.
VERSION ?=

.PHONY: help up down logs ps restart clean rebuild seed shell db-shell \
        release release-dry init-rds check-rds deploy rollback \
        prod-up prod-down prod-logs prod-ps

## --- local development -------------------------------------------------------

up: ## Build and start the whole stack (http://localhost:8080)
	$(COMPOSE) up --build -d
	@echo ""
	@echo "  LolSuit is starting -> http://localhost:8080"
	@echo "  Follow the logs with: make logs"

down: ## Stop everything, keep the database
	$(COMPOSE) down

clean: ## Stop everything and WIPE the database and uploads
	@printf "This deletes the database volume AND every uploaded image. Type yes: " && read ans && [ "$$ans" = "yes" ]
	$(COMPOSE) down -v

rebuild: ## Rebuild from scratch, ignoring the layer cache
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

logs: ## Follow logs (make logs S=server for one service)
	$(COMPOSE) logs -f $(S)

ps: ## What is running, and whether it is healthy
	$(COMPOSE) ps

restart: ## Restart one service (make restart S=worker)
	$(COMPOSE) restart $(S)

seed: ## Re-run the seed job (idempotent)
	$(COMPOSE) run --rm seed

shell: ## A shell in the API container
	$(COMPOSE) exec server /bin/bash

db-shell: ## A mysql prompt in the database container
	$(COMPOSE) exec db sh -c 'mysql -u"$$MYSQL_USER" -p"$$MYSQL_PASSWORD" "$$MYSQL_DATABASE"'

## --- releasing ---------------------------------------------------------------

release: ## Build+push both images to Docker Hub (make release VERSION=v1.0.1)
	@[ -n "$(VERSION)" ] || { echo "error: VERSION is required, e.g. make release VERSION=v1.0.1"; exit 1; }
	./prod/release.sh $(VERSION)

release-dry: ## Show what `make release` would run, without building
	@[ -n "$(VERSION)" ] || { echo "error: VERSION is required, e.g. make release-dry VERSION=v1.0.1"; exit 1; }
	./prod/release.sh $(VERSION) --dry-run

## --- deploying (run these ON THE SERVER) -------------------------------------

init-rds: ## Apply the schema to RDS (once, before the first deploy)
	cd prod && ./init-rds.sh

check-rds: ## Test RDS connectivity and list tables, changing nothing
	cd prod && ./init-rds.sh --check

deploy: ## Pull and go live (make deploy VERSION=v1.0.1)
	cd prod && ./deploy.sh $(VERSION)

rollback: ## Return to the previously deployed version
	cd prod && ./deploy.sh --rollback

prod-up: ## Start the production stack from the current .env TAG
	$(PROD_COMPOSE) up -d

prod-down: ## Stop the production stack (volumes survive)
	$(PROD_COMPOSE) down

prod-logs: ## Follow production logs (make prod-logs S=server)
	$(PROD_COMPOSE) logs -f $(S)

prod-ps: ## Production container status
	$(PROD_COMPOSE) ps

## --- meta --------------------------------------------------------------------

help: ## Show this help
	@echo ""
	@echo "  LolSuit - make targets"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} \
	     /^## ---/ { sub(/^## /, ""); printf "\n  \033[1m%s\033[0m\n", $$0; next } \
	     /^[a-zA-Z_-]+:.*?## / { printf "    \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""
