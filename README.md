# SciELO Tools

Plataforma web para ferramentas de apoio à produção e publicação científica da rede SciELO.

Stack: Python 3.14, Django 6, Wagtail 7.4.2, Celery, Redis, PostgreSQL.

Novas ferramentas são adicionadas como Django apps neste repositório.

---

## Desenvolvimento local

### Pré-requisitos

- Docker e Docker Compose
- Make

### Configuração

```bash
cp -r .envs.example/.local .envs/.local
make configure_git_hooks   # opcional
make build
make up
```

A aplicação fica disponível em http://localhost:8009.

### Comandos úteis

```bash
make help                  # lista todos os targets
make migrate               # aplica migrations
make shell                 # shell Django
make test                  # testes Django + pytest
make down                  # para os containers
```

---

## Estrutura do projeto

| App / diretório | Descrição |
|-----------------|-----------|
| `config/` | Configuração Django (settings, URLs, Celery) |
| `core/` | Modelos base, Wagtail home, templates e static |
| `core_settings/` | Configurações editáveis do site (nome, logo, favicon) |
| `users/` | `CustomUser` (`AUTH_USER_MODEL`) |
| `front/` | Marcação do front do artigo (API REST, Llama local, XML SPS 1.10) |
| `compose/` | Dockerfiles e scripts de inicialização |
| `requirements/` | Dependências Python (base, local, production) |

---

## Testes

```bash
make test
```

Ou via Docker Compose:

```bash
docker compose -f local.yml run --rm django python manage.py test --settings=config.settings.test
docker compose -f local.yml run --rm django pytest
```
