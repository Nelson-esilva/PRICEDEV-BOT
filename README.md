# PriceDev Bot

Sistema local de inteligência de preços para o mercado brasileiro.

O v1 descobre ofertas por conectores (Pelando e Shopee, ambos opt-in), grava histórico append-only, classifica oportunidades e expõe API + dashboard.

**Não usa Telegram como fonte.** Telegram, se ligado, é só publicação.

## Início rápido

Requisitos: Docker e Docker Compose, ou Python 3.12 + Node 20.

```bash
cp .env.example .env
docker compose up --build
```

O compose aponta as imagens para o Harbor privado (`172.21.70.155/pricedev/*`). Para build local sem Harbor, use `docker compose up --build` apenas em ambiente com acesso ao registry, ou rode backend/frontend direto (veja abaixo).

- API: http://localhost:8000/docs  
- Dashboard: http://localhost:5173  
- Health: http://localhost:8000/health  

Sem Docker (o `pyproject.toml` está em `backend/`, não na raiz):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=sqlite+aiosqlite:///./pricedev.db
uvicorn app.main:app --reload --app-dir .
```

Se o venv já estiver ativo na raiz do repositório:

```bash
pip install -e "./backend[dev]"
cd backend
DATABASE_URL=sqlite+aiosqlite:///./pricedev.db uvicorn app.main:app --reload --app-dir .
```

```bash
cd frontend
npm install
npm run dev
```

Por padrão `ENABLE_PELANDO=false` e `ENABLE_SHOPEE=false`. Ligue no `.env` a fonte que for usar.

## Wishlist (bot WhatsApp)

O cardápio-bot consulta as oportunidades aqui (**`GET /api/v1/opportunities/all`** — sem paginação, mesmo filtro da listagem) e usa a **watchlist** (`POST /api/v1/watchlist`) para acompanhar links por usuário.

Tenha em mente que o filtro `?since=` usa `COALESCE(source_created_at, detected_at)`, ou seja, considera a **idade real da oferta** na fonte, não a hora em que foi capturada.

Atualizar código: `git pull` no servidor (`~/pricedev`) → `docker compose pull` → `docker compose up -d`.

## Deploy (Harbor + Makefile)

Publica as imagens `backend` e `frontend` no Harbor como `latest`.

```bash
make publish HARBOR_PASSWORD=xxx
```

O Makefile:
- Faz `docker login` no Harbor com a senha passada como parâmetro.
- Builda `backend/` e `frontend/` (`linux/amd64`) e faz push para `172.21.70.155/pricedev/backend:latest` e `.../frontend:latest`.

Fluxo de publicação:
```bash
make publish HARBOR_PASSWORD=xxx          # 1. sobe as imagens
ssh administrator@172.21.70.150           # 2. no servidor
cd ~/pricedev && docker compose pull      # 3. puxa novas imagens
docker compose up -d                      # 4. recria os containers
```

Referência do servidor (`brmaobots01`):
- Pasta: `~/pricedev`
- Stack compose: `name: pricedev`
- Containers: `pricedev-backend`, `pricedev-frontend`, `pricedev-postgres`
- Volumes persistentes: `pricedev_pg` (PostgreSQL) e `pricedev_runtime` (sessão Telegram + dados)
- Imagens: `172.21.70.155/pricedev/backend:latest` e `frontend:latest`
- Portas: dashboard em `http://172.21.70.150:5173` (frontend) e backend interno `:8000`

⚠️ `docker compose down` preserva dados (`pricedev_pg`/`pricedev_runtime`); **nunca** use `down -v` nem remova volumes.

## Documentação

- Pesquisa Fase 0: `docs/00`–`docs/10`
- Plano v1: `docs/11-implementation-plan.md`
- Status: `docs/12-development-status.md`
- Integrações: `docs/13-integration-validation.md`

Referências de código de terceiros estão em `references/github/` e **não são executadas**.
