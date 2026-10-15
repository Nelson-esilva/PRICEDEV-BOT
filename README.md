# PriceDev Bot

Dois produtos no mesmo repositório:

- **Ops** (`frontend/`): dashboard interno — Ofertas, Canais Telegram, Hub. Inteligência de preços, não é o site público.
- **Vitrine** (`storefront/`): site consumidor (PromoDev) com Shopee + Mercado Livre oficiais e clique via `/go/{slug}` (afiliado stampado no servidor). Pelando e grupos **não** entram na vitrine.

O v1 descobre ofertas por conectores, grava histórico, classifica oportunidades e publica um catálogo `published_deals` para a vitrine.

## Início rápido

Requisitos: Docker e Docker Compose, ou Python 3.12 + Node 20.

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000/docs  
- Dashboard ops: http://localhost:5173  
- Vitrine: http://localhost:5174 (`cd storefront && npm install && npm run dev`)  
- Health: http://localhost:8000/health  

No Docker o **worker** (scheduler + Telegram) é um processo separado da API. Se `OPS_API_TOKEN` estiver no `.env`, o dashboard interno exige o mesmo valor em `VITE_OPS_TOKEN` (no Vite local: `frontend/.env` com `VITE_OPS_TOKEN=...`).  

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

## Documentação

- Pesquisa Fase 0: `docs/00`–`docs/10`
- Plano v1: `docs/11-implementation-plan.md`
- Status: `docs/12-development-status.md`
- Integrações: `docs/13-integration-validation.md`

Referências de código de terceiros estão em `references/github/` e **não são executadas**.
