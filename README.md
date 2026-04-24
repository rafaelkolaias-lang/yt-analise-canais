# youtube-analyzer

Sistema web para descoberta, monitoramento e analytics de canais do YouTube —
com foco em identificar nichos dark em aceleração e oportunidades de canais
novos.

Sucessor em arquitetura web do app desktop Tkinter anterior (agora removido —
toda a funcionalidade relevante foi portada para este stack web).

---

## Arquitetura

```
yt-analise-canais-web/
├── api/                   # Backend FastAPI (Python 3.11+)
│   ├── app/
│   │   ├── core/          # config, database, crypto, scheduler
│   │   ├── routers/       # health, settings, discovery, monitoring, sync, analytics
│   │   ├── services/      # regras de negócio
│   │   ├── schemas/       # Pydantic
│   │   └── models/        # SQLAlchemy
│   ├── migrations/        # Alembic
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── .env.example
│   └── .env               # ← NÃO commitado
├── web/                   # Frontend Next.js 15 (App Router, TS, React 19)
│   ├── app/               # páginas
│   ├── components/        # Sidebar, Toaster, GlobalSyncIndicator, Skeleton, ErrorCard…
│   ├── lib/
│   ├── package.json
│   ├── next.config.ts     # output: "standalone" (pro Dockerfile)
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── .env.example
│   └── .env.local         # ← NÃO commitado
├── docs/
├── start-dev.bat          # atalho: abre api + web em 2 terminais
├── !projeto.md            # mapa do projeto (para IA e humano)
└── !executar.md           # plano de fases
```

### Serviços no EasyPanel

- `youtube-analyzer-web` — Next.js (porta 3000)
- `youtube-analyzer-api` — FastAPI (porta 8000)
- `youtube-analyzer-banco` — MySQL 8 (host interno `banco_youtube-analyzer-banco:3306`)

---

## Rodar localmente

### Pré-requisitos

- Python 3.11+
- Node.js 18.17+ (testado em 24.13)
- MySQL acessível (XAMPP local **ou** banco do EasyPanel via IP público)

### 1. Backend (API)

```bash
cd api
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt

# Configurar env
cp .env.example .env
# Editar DATABASE_URL e APP_SECRET_KEY

# Primeira vez — criar schema e settings default
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m app.seed

uvicorn app.main:app --reload --port 8000
```

Abrir: <http://localhost:8000/docs>

Healthchecks:
- <http://localhost:8000/health> — app
- <http://localhost:8000/health/db> — conexão com banco

### 2. Frontend (Web)

```bash
cd web
npm install
cp .env.example .env.local
# NEXT_PUBLIC_API_URL já aponta para http://localhost:8000

npm run dev
```

Abrir: <http://localhost:3000>

### Atalho: `start-dev.bat`

Duplo-clique em [start-dev.bat](start-dev.bat) abre 2 terminais já com a API e
o Web rodando.

---

## Variáveis de ambiente

### `api/.env`

| Var | Descrição |
|---|---|
| `APP_ENV` | `development` \| `production` |
| `APP_NAME` | Nome do app (aparece na resposta do `/`). |
| `DATABASE_URL` | Connection string MySQL: `mysql+pymysql://user:pass@host:port/db`. Senha com caracteres especiais (`$`, `@`, `:`) precisa ser URL-encoded. |
| `APP_SECRET_KEY` | Chave mestra para cifrar secrets (YouTube API keys) no banco. **Se perdida, os secrets cifrados ficam irrecuperáveis.** Gerar com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `SYNC_INTERVAL_HOURS` | Default `12`. Também é lido do banco (`app_settings.sync_interval_hours`) — o env serve como fallback se o banco ainda estiver vazio. |
| `CORS_ORIGINS` | Origens permitidas separadas por vírgula. Em prod, incluir o domínio do frontend. |

### `web/.env.local`

| Var | Descrição |
|---|---|
| `NEXT_PUBLIC_API_URL` | URL pública da API. Em dev: `http://localhost:8000`. Em prod: URL do serviço `youtube-analyzer-api` no EasyPanel. É **lida em build time** pelo Next, não em runtime. |

---

## Deploy no EasyPanel

Deploy via Git push. O EasyPanel lê os `Dockerfile` em `api/` e `web/` e
builda automaticamente quando há commit novo.

### 1. Criar os 3 serviços no EasyPanel

No projeto `youtube-analyzer` do EasyPanel:

#### a) `youtube-analyzer-banco` (MySQL 8)
Já provisionado. Host interno: `banco_youtube-analyzer-banco:3306`.

#### b) `youtube-analyzer-api` (FastAPI)
- **Source**: apontar para o repo Git, branch `main`, build context `api/`.
- **Dockerfile**: `api/Dockerfile` (detectado automaticamente).
- **Porta**: 8000.
- **Env vars**:
  ```
  APP_ENV=production
  APP_NAME=youtube-analyzer-api
  DATABASE_URL=mysql+pymysql://youtubeanalyzer:SENHA_URL_ENCODED@banco_youtube-analyzer-banco:3306/youtube-analyzer-banco
  APP_SECRET_KEY=<gerar novo, diferente do dev>
  SYNC_INTERVAL_HOURS=12
  CORS_ORIGINS=https://youtube-analyzer-web.SEU-SUBDOMINIO.easypanel.host
  ```
  > **Importante**: `APP_SECRET_KEY` de produção precisa ser gerada separadamente
  > do dev. Se ela trocar depois do primeiro deploy, as YouTube API keys
  > cifradas no banco ficam irrecuperáveis — precisará reinserir via
  > `/configuracoes`.

#### c) `youtube-analyzer-web` (Next.js)
- **Source**: mesmo repo, build context `web/`.
- **Dockerfile**: `web/Dockerfile`.
- **Porta**: 3000.
- **Env vars / build args**:
  ```
  NEXT_PUBLIC_API_URL=https://youtube-analyzer-api.SEU-SUBDOMINIO.easypanel.host
  ```
  > **Importante**: `NEXT_PUBLIC_*` é lido em **build time**. Se o EasyPanel
  > fizer o build sem receber essa var como build arg, o frontend sai com
  > `http://localhost:8000` embutido. No EasyPanel, env vars normalmente são
  > passadas tanto no build quanto no run — confirmar nos logs do build se
  > aparecer `NEXT_PUBLIC_API_URL=https://…`.

### 2. Inicializar o banco

Após o primeiro deploy da API, abrir o shell do container `youtube-analyzer-api`
no EasyPanel e rodar:

```bash
alembic upgrade head
python -m app.seed
```

Isso cria o schema (11 tabelas) e popula as 15 settings default. Idempotente,
seguro de rodar de novo.

### 3. Configurar a YouTube API key

Abrir o frontend (`youtube-analyzer-web`), ir em **Configurações → API do
YouTube**, colar a(s) key(s) da Data API v3. Elas são cifradas com Fernet
(AES-128 + HMAC-SHA256) antes de persistir — nunca retornam em texto plano.

### 4. Smoke test

- Dashboard deve mostrar os cards de API e Banco **verdes**.
- Clicar em **Verificar agora** dispara um sync manual. Com 0 canais
  monitorados, só retorna rapidamente sem erro.
- Adicionar um canal via **Descoberta** e depois rodar sync outra vez — os
  snapshots começam a popular.

### Atualizações futuras

`git push` no branch configurado dispara rebuild automático no EasyPanel.
Migrações novas: rodar `alembic upgrade head` no shell do container. Settings
novas (`app.seed.py`): rodar `python -m app.seed`.

---

## Segurança

- `.env*` são ignorados pelo git (exceto `.env.example`). Conferir com:
  ```bash
  git check-ignore -v api/.env web/.env.local
  ```
- Credenciais reais **nunca** são commitadas.
- YouTube API keys são armazenadas cifradas no banco com Fernet (AES-128 +
  HMAC-SHA256), chave derivada de `APP_SECRET_KEY` via SHA-256.
- Em produção, gerar um `APP_SECRET_KEY` diferente do de dev, e configurá-lo
  apenas no env do container no EasyPanel.

---

## Status

Sistema completo — fases 0–8 concluídas. Ver [!executar.md](!executar.md) para
histórico de entregas e [!projeto.md](!projeto.md) para o mapa completo do
projeto (endpoints, schema, fluxos críticos, armadilhas conhecidas).
