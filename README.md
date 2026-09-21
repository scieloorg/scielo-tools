# SciELO Tools

Plataforma web para ferramentas de apoio à produção e publicação científica da rede SciELO.

**Stack:** Python 3.14, Django 6.0.5, Wagtail 8.0, Celery 5.3.6, Redis 8, PostgreSQL 18.

| Componente | Versão | Onde está definido |
|------------|--------|--------------------|
| Python | 3.14 | `compose/local/django/Dockerfile`, `pyproject.toml` (`target-version`) |
| Django | 6.0.5 | `requirements/base.txt` |
| Wagtail | 8.0 | `requirements/base.txt` |
| Django REST framework | 3.18.1 | `requirements/base.txt` |
| Celery | 5.3.6 | `requirements/base.txt` |
| redis (cliente Python) | 7.4.0 | `requirements/base.txt` |
| Redis (serviço local) | 8 | `local.yml` |
| PostgreSQL (imagem) | 18.4 | `compose/production/postgres/Dockerfile` |
| packtools (SPS) | 4.17.6 | `requirements/base.txt` |
| Ruff (dev) | 0.16.8 | `requirements/local.txt` |

Novas ferramentas são adicionadas como Django apps neste repositório.

---

## Desenvolvimento local

### Pré-requisitos

- Docker e Docker Compose
- Make
- Python 3.14 (recomendado) para rodar o Django no host com `./local.sh`

### Variáveis de ambiente

```bash
cp -r .envs.example/.local .envs/.local
make configure_git_hooks   # opcional
```

### Opção 1 — tudo no Docker

```bash
make build
make up
```

A aplicação fica em http://localhost:8000 (container `django`).

### Opção 2 — Django no host com `./local.sh`

Útil para depurar no IDE: Postgres, Redis, Mailhog e Celery continuam no Docker; o `runserver` roda na máquina.

**Primeira vez:**

```bash
make build                 # imagens postgres/redis etc.
python3.14 -m venv .venv
.venv/bin/pip install -r requirements/local.txt
chmod +x local.sh          # se necessário
```

**Subir o ambiente:**

```bash
./local.sh
```

O script:

1. Verifica `.envs/.local/.django` e `.postgres` (mensagem de erro indica o `cp` acima se faltarem).
2. Usa `.venv/bin/python`, ou `python3.14`, ou `python3`, e exige Django instalado no ambiente escolhido.
3. Para o container `django` e sobe `postgres`, `redis`, `mailhog`, `celeryworker` e `celerybeat` via `local.yml`.
4. Define `USE_DOCKER=no`, `DJANGO_SETTINGS_MODULE=config.settings.local` e aponta Postgres/Redis/Mailhog para `127.0.0.1` (portas publicadas pelo Compose: Postgres **5439**, Redis **6399**).
5. Aponta `REFERENCE_URL`, `FRONT_URL` e `BODY_URL` para Llama/Ollama em **http://127.0.0.1:11434** (serviço no host; o serviço `ollama` no Compose está comentado).
6. Se existir `../packtools` ao lado do repositório, instala-o em modo editable no venv.
7. Aguarda o Postgres, executa `migrate` e inicia `runserver_plus` em http://localhost:8000 (host `0.0.0.0`, porta **8000**).

Mailhog (e-mail de desenvolvimento): http://localhost:8029.

Variáveis opcionais antes de `./local.sh`:

| Variável | Padrão | Uso |
|----------|--------|-----|
| `HOST_POSTGRES_PORT` | `5439` | Porta do Postgres no host |
| `HOST_REDIS_PORT` | `6399` | Porta do Redis no host |
| `RUNSERVER_HOST` | `0.0.0.0` | Bind do `runserver_plus` |
| `RUNSERVER_PORT` | `8000` | Porta HTTP |
| `LLAMA_HOST` | `127.0.0.1:11434` | Ollama/Llama local para marcação |
| `COMPOSE_FILE` | `local.yml` | Ficheiro Compose alternativo |

### Comandos úteis

```bash
make help                  # lista todos os targets
make django_migrate        # python manage.py migrate
make django_shell          # shell Django interativo
make django_createsuperuser
make stop                  # para os serviços do Compose
make lint                  # ruff check + ruff format --check
make format                # ruff format
make test                  # pytest (exclui marca llama)
```

Com `./local.sh` (Django no host), use o mesmo `manage.py` do venv, por exemplo `.venv/bin/python manage.py migrate`.

### Autenticação, senha e tokens

Com stack Docker (`make up` ou serviços já levantados pelo `./local.sh`):

```bash
make django_createsuperuser

docker compose -f local.yml run --rm django python manage.py changepassword NOME_UTILIZADOR

docker compose -f local.yml run --rm django python manage.py generate_password
docker compose -f local.yml run --rm django python manage.py generate_password --length 24
```

Validar uma senha candidata contra `AUTH_PASSWORD_VALIDATORS` (`config/settings/base.py`: comprimento mínimo, senha comum, numérica, similaridade ao utilizador):

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
User = get_user_model()
user = User.objects.filter(username='admin').first()
password = 'coloque-a-senha-aqui'
try:
    validate_password(password, user=user)
    print('Senha aceite pelos validadores.')
except ValidationError as e:
    print('Senha rejeitada:', '; '.join(e.messages))
"
```

Confirmar credenciais (login Django) e obter JWT para a API:

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from django.contrib.auth import authenticate
user = authenticate(username='UTILIZADOR', password='SENHA')
print('OK' if user else 'Falhou')
"

eval "$(make bearer_token JWT_USERNAME=UTILIZADOR JWT_PASSWORD=SENHA)"
echo "$TOKEN"
```

O target `bearer_token` grava também `.token` e imprime `export TOKEN=...` para usar em `curl -H "Authorization: Bearer $TOKEN"`.

Tokens da API Wagtail (Headless):

```bash
docker compose -f local.yml run --rm django python manage.py api_tokens list
docker compose -f local.yml run --rm django python manage.py api_tokens create --help
```

Fixtures de utilizadores/grupos (`auth`):

```bash
make django_dump_auth
make django_load_auth
```

Apenas desenvolvimento local (`DEBUG=True`): `set_fake_passwords` define a mesma senha para todos os utilizadores — não usar fora de ambiente local.

### Verificações do projeto

```bash
docker compose -f local.yml run --rm django python manage.py check
docker compose -f local.yml run --rm django python manage.py check --deploy
docker compose -f local.yml run --rm django python manage.py sendtestemail destino@example.com
```

E-mail de teste com Mailhog levantado: interface em http://localhost:8029.

Deteção de segredos hardcoded no código (regras Bandit `S` via Ruff):

```bash
make lint
ruff check --select S .
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
| `body/` | Marcação do corpo do artigo (API REST, Llama local, XML SPS 1.10) |
| `compose/` | Dockerfiles e scripts de inicialização |
| `requirements/` | Dependências Python (base, local, production) |

---

## Qualidade de código

Lint e formatação usam **Ruff** (`pyproject.toml` na raiz). Não use Black nem isort.

### Comandos

Via Docker (padrão do Makefile):

```bash
make lint                  # ruff check . && ruff format --check .
make format                # ruff format .
make lint-fix              # ruff check --fix . && ruff format .
```

Com venv local (após `pip install -r requirements/local.txt`), na raiz do repositório:

```bash
ruff check --fix path/to/file.py   # lint com correção automática
ruff format path/to/file.py        # formatação (rodar depois do check --fix)
ruff check .                       # só verificar
ruff format --check .              # só verificar formatação
```

Ordem recomendada ao editar ficheiros: `ruff check --fix` e depois `ruff format`.

### Opções de formatação (`[tool.ruff]` e `[tool.ruff.format]`)

| Opção | Valor | Efeito |
|-------|--------|--------|
| `line-length` | `88` | Quebra de linha (alinhado ao estilo Black) |
| `target-version` | `py314` | Sintaxe Python 3.14 |
| `quote-style` | `double` | Strings com aspas duplas |

Pastas ignoradas pelo Ruff (lint e format): `.git`, `.venv`, `venv`, `dist`, `build`, `node_modules`, `staticfiles`, `*/migrations/*`, `docs`.

### Lint (`[tool.ruff.lint]`)

Regras ativas: `E`, `F`, `I` (imports/isort), `UP` (pyupgrade), `B` (bugbear), `S` (Bandit). Ignorado globalmente: `S101` (`assert` em testes de produção). Imports de apps do projeto em `known-first-party` (`config`, `core`, `body`, `front`, `reference`, etc.). Exceções por ficheiro em `[tool.ruff.lint.per-file-ignores]`.

Pytest lê `[tool.pytest.ini_options]` do mesmo `pyproject.toml`.

---

## Testes

```bash
make test
```

Ou via Docker Compose:

```bash
docker compose -f local.yml run --rm django pytest --reuse-db -m "not llama"
docker compose -f local.yml run --rm django python manage.py test --settings=config.settings.test
```
