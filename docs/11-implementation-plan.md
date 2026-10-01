# 11 — Plano de implementação do v1

**Data:** 2026-10-01  
**Precedência:** prompt mestre v2.0 > `docs/10-constraints-single-affiliate-and-latency.md` > ADRs compatíveis.

## Escopo exato do v1

Monólito modular Python (FastAPI) + PostgreSQL + dashboard React. Modo mock padrão, sem credenciais.

| Incluído | Fora |
|---|---|
| Fonte simulada contínua | Keepa, Creators API, PA-API, scrape Amazon |
| Histórico append-only (Decimal) | Telegram como fonte |
| Motor PROVISIONAL / HISTORICALLY_VALIDATED / INSUFFICIENT_HISTORY / PRICE_ANOMALY_CANDIDATE | WhatsApp Web, K8s, microserviços |
| API REST de oportunidades | Coleta real Pelando até `ENABLE_PELANDO=true` **e** ToS ok |
| Adaptador Shopee (flag off) | Múltiplas redes de afiliados |
| Adaptador Pelando isolado + fixtures (flag off) | Bypass Cloudflare |
| Lomadee stub (flag off, link direto se falhar) | |
| Telegram **saída** (flag off) | |
| Dashboard local | |
| Métricas de latência | |

## Layout no workspace

`docs/` e `references/` permanecem na raiz. Código em `backend/` e `frontend/`. Referências não são movidas nem executadas.

## Núcleo

1. `SourceConnector.poll()` → `NormalizedOffer`.
2. Pipeline: dedup → identidade `(marketplace, native_product_id, variant_id, merchant_id)` → observação (só se o preço mudou) → estatísticas **excluindo** a observação atual → motor → oportunidade.
3. Preço Pelando nunca vira `verified_price`.
4. `priceDiscountRate` Shopee é auxiliar.
5. Sem afiliado: `final_purchase_url` = URL direta válida.

## Polling

Mock: 15 s (dev). Pelando (se ligado): 60 s. Shopee (se ligado): 120 s. Configurável. Rate limit 1 rps no cliente Pelando (ideia BSD, código próprio).

## Testes

Pytest no motor (relógio injetado), ingestão, API mock, publicação. Sem afirmar SLO 180 s com dados simulados.

## Entrega desta execução

Ambiente local executável em mock: histórico, classificações, API, testes, dashboard e conectores reais **desligados**.
