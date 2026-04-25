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

## Manutenção — o que fazer se…

### …a URL pública da API mudar

Por exemplo, se você mover de subdomínio EasyPanel ou apontar um domínio
próprio. **Dois lugares precisam ser atualizados** (não tem auto-detecção):

1. **Env var do `youtube-analyzer-web`** no EasyPanel: trocar `NEXT_PUBLIC_API_URL`
   pra a nova URL. Como `NEXT_PUBLIC_*` é embutido em build time, é necessário
   **redeployar o `-web`** (não basta reiniciar).
2. **Env var do `youtube-analyzer-api`** no EasyPanel: trocar `CORS_ORIGINS`
   pra incluir a nova URL do frontend (senão o navegador bloqueia).

> Se em algum momento decidirmos hardcodar a URL da API como fallback dentro
> do código (em vez de depender só da env var), o lugar é
> [web/lib/api.ts](web/lib/api.ts) na constante `API_URL` (linha 1–2).

### …a senha do banco for rotacionada

1. Trocar `DATABASE_URL` na env var do `-api` no EasyPanel (lembrar de
   URL-encodar a nova senha).
2. Reiniciar (não precisa rebuildar — env var é runtime).
3. Atualizar [SECRETS.local.md](SECRETS.local.md) localmente (gitignorado).

### …`APP_SECRET_KEY` for trocada

⚠️ **Cuidado.** As YouTube API keys cifradas no banco usam essa chave —
trocar `APP_SECRET_KEY` torna os secrets cifrados **irrecuperáveis** (Fernet
não tem backdoor).

Procedimento seguro:
1. Antes de trocar, no `/configuracoes` do frontend, **anotar** as YouTube
   API keys atuais (você só consegue colar de novo, não decifrar via API).
2. Trocar a env var `APP_SECRET_KEY` no `-api`.
3. Reiniciar o `-api`.
4. Voltar em `/configuracoes` e **colar de novo** a(s) key(s).

### …adicionar/remover settings default

Editar [api/app/seed.py](api/app/seed.py) (lista `DEFAULT_SETTINGS`),
commitar, push, redeployar `-api`. Depois, no shell do container:
```bash
python -m app.seed
```
O seed é idempotente (só insere o que ainda não existe). Settings antigas
removidas do código continuam no banco — apagar manualmente via SQL se
quiser limpar.

### …trocar o intervalo de sync sem rebuildar

`Configurações → Sincronização → sync_interval_hours` no frontend, ou
`PUT /api/settings/sync_interval_hours` direto. O scheduler reagenda em
runtime — não precisa restart.

### …adicionar um domínio próprio (em vez do subdomínio EasyPanel)

1. Apontar o DNS (registro CNAME) pra `<subdomínio>.easypanel.host`.
2. EasyPanel → serviço (`-web` ou `-api`) → aba **Domínios** → adicionar
   o domínio próprio com HTTPS ligado (Let's Encrypt automático).
3. Atualizar `NEXT_PUBLIC_API_URL` (no `-web`) e `CORS_ORIGINS` (no `-api`)
   se mudar a URL da API.
4. Redeployar `-web` (por causa do `NEXT_PUBLIC_*` em build time).

### …aplicar uma migração nova (Alembic) em produção

Após `git push` com migration nova:

1. EasyPanel rebuilda automaticamente o container `-api` (ou clicar
   "Implantar" se não houver auto-deploy).
2. Esperar o container ficar verde.
3. Abrir o shell do `-api` (botão `>_` → Bash).
4. Rodar:
   ```bash
   alembic upgrade head
   ```
5. Validar: `curl https://API/api/monitoring/channels` deve voltar 200.

> ⚠️ DDL em produção é destrutivo se mal feito (DROP COLUMN, ALTER incompatível
> etc.). Migrações deste projeto até hoje só fizeram `ADD COLUMN nullable`,
> que é seguro. Se um dia precisar mudar tipos ou apagar coluna, fazer
> backup do banco antes.

### …importar canais do projeto desktop antigo

Use [scripts/import_legacy.py](scripts/import_legacy.py). Lê
`monitorados.json`, `canais_listados.csv` e `config.json` da pasta
`E:\Automacao-YT\yt-analise-canais\dados\`.

```bash
# Dry-run (mostra o plano, não escreve)
api/.venv/Scripts/python.exe scripts/import_legacy.py --dry-run

# Local (XAMPP)
api/.venv/Scripts/python.exe scripts/import_legacy.py

# Produção (EasyPanel) — atenção ao --skip-keys se já configurou
# as YouTube API keys via UI em /configuracoes
api/.venv/Scripts/python.exe scripts/import_legacy.py \
    --base-url https://banco-youtube-analyzer-api.cpgdmb.easypanel.host \
    --skip-keys
```

Idempotente. Os 11 canais do `monitorados.json` ficam como `active`; os 232
do `canais_listados.csv` (descontadas duplicatas e canais já active) ficam
como `paused`. Canais deletados/banidos no YouTube falham com HTTP 400 —
esperado, são lixo histórico. Custo de quota: ~1 unit por canal criado.

### …popular thumbnails que ficaram em branco (backfill em lote)

Quando se adiciona o campo `thumbnail_url` a um banco que já tem registros,
ou se importa canais antes do code do `_pick_thumbnail` estar rodando, eles
ficam com `thumbnail_url=NULL`. Use [scripts/backfill_thumbnails.py](scripts/backfill_thumbnails.py)
pra popular em lote.

```bash
# Dry-run (não chama YouTube nem grava)
api/.venv/Scripts/python.exe scripts/backfill_thumbnails.py --dry-run

# Pra valer (local OU prod — usa Settings da venv da api/)
api/.venv/Scripts/python.exe scripts/backfill_thumbnails.py

# Só canais ou só vídeos
api/.venv/Scripts/python.exe scripts/backfill_thumbnails.py --skip-videos
api/.venv/Scripts/python.exe scripts/backfill_thumbnails.py --skip-channels
```

Custo de quota: **1 unit por lote de 50 registros** (vs 3 units por canal
se fosse via `snapshot_channel`). 218 canais → 5 lotes → 5 units total.
Só toca em rows com `thumbnail_url IS NULL` (idempotente).

> O script roda direto contra o banco usando o ORM da api/ (não via HTTP).
> Por isso depende do `api/.venv` e da `DATABASE_URL` no `api/.env`.
> Pra rodar contra prod a partir da máquina local, troque temporariamente
> a `DATABASE_URL` ou rode pelo shell do container EasyPanel.

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
