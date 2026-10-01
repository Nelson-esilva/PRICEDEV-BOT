# 12 — Status de desenvolvimento

**Data:** 2026-10-01  
**Execução:** primeira implementação do v1 (núcleo local)

## Componentes implementados

- Monólito FastAPI com PostgreSQL/SQLite, histórico append-only e Decimal.
- Fonte simulada (`mock`) com seed de 30 dias + queda de preço contínua.
- Motor PROVISIONAL / HISTORICALLY_VALIDATED / INSUFFICIENT_HISTORY / PRICE_ANOMALY_CANDIDATE.
- API REST (`/health`, oportunidades, produtos, histórico, estatísticas, fontes).
- Dashboard React (polling 5s, badges de classificação, gráfico de histórico).
- Adaptadores Shopee, Pelando e Lomadee **desligados** por padrão.
- Telegram somente como publicador opcional, provisórias bloqueadas.
- Docker Compose e testes pytest.

## Testes executados

```text
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
# 41 passed in 1.20s (2026-10-01)
```

Cobertura: motor histórico, ingestão/dedup, API, publicação Telegram, fixtures Pelando, assinatura Shopee, URLs, histórico por dia.

## Arquivos principais

`backend/app/**`, `backend/tests/**`, `frontend/src/**`, `docker-compose.yml`, `.env.example`, `docs/11-13`.

## Bloqueios

- Pelando: API interna; coleta real exige confirmação de ToS. Flag `ENABLE_PELANDO=false`.
- Shopee: adaptador pronto; precisa App ID/Secret da conta. Docs oficiais confirmam SHA256 por concatenação (não HMAC).
- `productOfferV2` **não** tem sort “mais recentes” (1=relevância … 5=comissão). Recência oficial está em `shopeeOfferV2.sortType=1`.
- Lomadee: stub; contrato vivo não testado com credencial.
- SLO de 180s: medido sobre amostras persistidas; **não** é garantia, e dados mock não comprovam o SLO.

## Pendências

- Ativar Shopee quando houver credenciais.
- Decisão explícita sobre ToS do Pelando antes de ligar o conector.
- Cadastro Lomadee se houver interesse em comissão multi-loja.
- Publicação Telegram quando houver bot.

## Próxima etapa

Validar conectores reais autorizados (Shopee primeiro) e acompanhar métricas de latência com tráfego verdadeiro.
