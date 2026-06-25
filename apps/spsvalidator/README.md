# spsvalidator

Aplicação standalone para validação de pacotes SPS (`.zip`) com Flask, Pywebview e SQLite.

## Executar em desenvolvimento

```bash
cd apps/spsvalidator
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
spsvalidator
```

## Modo navegador (sem janela Pywebview)

```bash
spsvalidator --browser
```

Abre em `http://127.0.0.1:5000`.

## Build por sistema operacional

Scripts em `packaging/`.

```bash
cd apps/spsvalidator
source .venv/bin/activate
bash packaging/build_macos.sh
```

Saída: `dist/spsvalidator.app`

## Se o `.app` não abrir ao clicar

1. Rebuild após atualizar o código (build antigo pode não chamar `main()` nem incluir templates).
2. Rode pelo terminal para ver erros:

```bash
apps/spsvalidator/dist/spsvalidator.app/Contents/MacOS/spsvalidator
```

3. Em desenvolvimento, prefira:

```bash
spsvalidator --browser
```

## Erro `No module named 'pkg_resources'`

O `packtools` ainda depende de `pkg_resources` (fornecido pelo `setuptools<82`). Após atualizar o código:

```bash
cd apps/spsvalidator
source .venv/bin/activate
pip install -e ".[dev]"
bash packaging/build_macos.sh
open dist/spsvalidator.app
```

## Erro `No module named 'requests'` (ou `request`)

O `packtools` usa dependências transitivas (`requests`, `tenacity`, `langdetect`) que já estão no `pyproject.toml`. Reinstale e rebuild:

```bash
cd apps/spsvalidator
source .venv/bin/activate
pip install -e ".[dev]"
bash packaging/build_macos.sh
```

Dados locais ficam em `~/.spsvalidator/spsvalidator.sqlite3`.
