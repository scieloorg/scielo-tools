COMPOSE_FILE ?= local.yml

export SCMS_BUILD_DATE := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
export SCMS_VCS_REF := $(shell git rev-parse --short HEAD)
export SCMS_WEBAPP_VERSION := v0.0.3-qa

default: build

help: ## Show this help
	@echo 'Usage: make [target] [COMPOSE_FILE=file]'
	@echo ''
	@echo 'Targets:'
	@egrep '^(.+)\:\ .*##\ (.+)' ${MAKEFILE_LIST} | sed 's/:.*##/#/' | column -t -c 1 -s "#"
	@echo ''

app_version: ## Show version of webapp
	@echo "Version: $(SCMS_WEBAPP_VERSION)"

latest_commit:  ## Show last commit ref
	@echo "Latest commit: $(SCMS_VCS_REF)"

build_date: ## Show build date
	@echo "Build date: $(SCMS_BUILD_DATE)"

configure_git_hooks: ## Configure git hooks
	cp -fa .git-hook-commit-msg .git/hooks/commit-msg
	ln -sf ../../.git-hook-commit-msg .git/hooks/commit-msg

############################################
## docker compose shortcuts
############################################

build:  ## Build app using $(COMPOSE_FILE)
	docker compose -f $(COMPOSE_FILE) build

build_no_cache:  ## Build app without cache
	docker compose -f $(COMPOSE_FILE) build --no-cache

up:  ## Start app
	docker compose -f $(COMPOSE_FILE) up -d

logs: ## See all app logs
	docker compose -f $(COMPOSE_FILE) logs -f

stop:  ## Stop all services
	docker compose -f $(COMPOSE_FILE) stop

restart:  ## Restart all services
	docker compose -f $(COMPOSE_FILE) restart

ps:  ## List containers
	docker compose -f $(COMPOSE_FILE) ps

rm:  ## Remove all containers
	docker compose -f $(COMPOSE_FILE) rm -f

django_shell:  ## Open Django shell
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py shell

django_createsuperuser: ## Create a superuser
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py createsuperuser

django_bash: ## Open bash in django container
	docker compose -f $(COMPOSE_FILE) run --rm django bash

test: ## Run tests (pytest default, excludes llama eval)
	docker compose -f $(COMPOSE_FILE) run --rm django pytest --reuse-db -m "not llama"

test-llama: ## Run Llama reference eval tests (requires Ollama)
	docker compose -f $(COMPOSE_FILE) run --rm django pytest --reuse-db -m llama reference/tests/test_references.py

test-fast: ## Run tests (pytest failfast)
	docker compose -f $(COMPOSE_FILE) run --rm django pytest -x --reuse-db -m "not llama"

test-cov: ## Run tests with coverage (reference, fail under 100%)
	docker compose -f $(COMPOSE_FILE) run --rm django pytest --reuse-db -m "not llama" \
		--cov=reference --cov-report=term-missing --cov-fail-under=100 \
		reference/tests

test-fresh: ## Recreate test database and run pytest
	docker compose -f $(COMPOSE_FILE) run --rm django pytest --create-db

django_test: ## Run tests (legacy Django runner)
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py test --settings=config.settings.test

django_fast: ## Run tests (legacy Django runner failfast)
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py test --settings=config.settings.test --failfast

pytest: test ## Alias: pytest default

pytest_fast: test-fast ## Alias: pytest failfast

pytest_cov: test-cov ## Alias: pytest coverage

django_makemigrations: ## Run makemigrations
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py makemigrations

django_migrate: ## Run migrate
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py migrate

django_makemessages: ## Run makemessages
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py makemessages --all

django_compilemessages: ## Run compilemessages
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py compilemessages

wagtail_sync: ## Sync wagtail page translation fields
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py sync_page_translation_fields

wagtail_update_translation_field: ## Update wagtail translation fields
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py update_translation_fields

django_dump_auth: ## Dump auth data to fixtures/auth.json
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py dumpdata auth --indent=2 --output=fixtures/auth.json

django_load_auth: ## Load auth data from fixtures/auth.json
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py loaddata --database=default fixtures/auth.json

remove_all_references: ## Delete all cached Reference / ElementCitation rows
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py remove_all_references --no-input

remove_all_front: ## Delete all cached Front rows
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py remove_all_front --no-input

remove_all_body: ## Delete all cached Body rows
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py remove_all_body --no-input

remove_all_manuscript: ## Delete all Manuscript rows
	docker compose -f $(COMPOSE_FILE) run --rm django python manage.py remove_all_manuscript --no-input

dump_data: ## Dump database into timestamped .sql file
	docker compose -f $(COMPOSE_FILE) exec postgres pg_dumpall -c -U debug > dump_$$(date +%d-%m-%Y"_"%H_%M_%S).sql

restore_data: ## Restore database from backup/latest.sql
	docker compose -f $(COMPOSE_FILE) exec -T postgres psql -U debug < backup/latest.sql

volume_down: ## Remove all volumes
	docker compose -f $(COMPOSE_FILE) down -v

############################################
## ollama / reference
############################################

REFERENCE_MODEL ?= llama3.2:3b

ollama_pull: ## Pull Llama model into local ollama container
	docker compose -f $(COMPOSE_FILE) exec ollama ollama pull $(REFERENCE_MODEL)

############################################
## JWT
############################################

JWT_USERNAME ?=
JWT_PASSWORD ?=

bearer_token: ## eval "$$(make bearer_token JWT_USERNAME=u JWT_PASSWORD=p)" then curl -H "Authorization: Bearer $$TOKEN"
	@test -n "$(JWT_USERNAME)" && test -n "$(JWT_PASSWORD)" || (echo 'Usage: eval "$$(make bearer_token JWT_USERNAME=user JWT_PASSWORD=pass)"' >&2 && exit 1)
	@TOKEN=$$(docker compose -f $(COMPOSE_FILE) run --rm -T \
		-e JWT_USERNAME=$(JWT_USERNAME) \
		-e JWT_PASSWORD=$(JWT_PASSWORD) \
		django python manage.py shell -c "from django.contrib.auth import authenticate; from rest_framework_simplejwt.tokens import RefreshToken; import os, sys; user = authenticate(username=os.environ['JWT_USERNAME'], password=os.environ['JWT_PASSWORD']); sys.exit(1) if not user else print(RefreshToken.for_user(user).access_token)" \
		2>/dev/null | tr -d '\r' | grep -Eo 'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+' | tail -n 1); \
	if [ -z "$$TOKEN" ]; then echo "Failed to obtain JWT (check JWT_USERNAME/JWT_PASSWORD)" >&2; exit 1; fi; \
	printf '%s\n' "$$TOKEN" > .token; \
	printf "export TOKEN='%s'\n" "$$TOKEN"

############################################
## Cleanup
############################################

clean_migrations: ## Remove all migration files
	find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
	find . -path "*/migrations/*.pyc" -delete

clean_container: ## Remove all containers
	docker rm $$(docker ps -a -q --no-trunc)

clean_dangling_images: ## Remove dangling images
	docker image prune -f

clean_dangling_volumes: ## Remove dangling volumes
	docker volume rm $$(docker volume ls -f dangling=true -q)

clean_project_images: ## Remove project images
	docker rmi -f $$(docker images --filter=reference='*scielo_tools*' -q)
