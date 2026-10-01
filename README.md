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

## Documentação

- Pesquisa Fase 0: `docs/00`–`docs/10`
- Plano v1: `docs/11-implementation-plan.md`
- Status: `docs/12-development-status.md`
- Integrações: `docs/13-integration-validation.md`

Referências de código de terceiros estão em `references/github/` e **não são executadas**.
