# 09 — Arquitetura proposta (consequência da investigação)

**Data:** 2026-10-01  
**Status:** proposta de longo prazo. **Não implementar** até autorização explícita.

**Recorte v1 (restrições de cadastro, latência e custo):** ver `docs/10-constraints-single-affiliate-and-latency.md`. Sob essas restrições o v1 **não** usa Keepa, Creators API **nem canais Telegram como fonte**. A descoberta é Pelando `/feed/v2/recents` (a mesma API JSON dos bots de grupos) + Shopee Affiliate. Telegram só publica. Monetização: Shopee + no máximo um cadastro Lomadee.

Este desenho de longo prazo continua válido se no futuro houver API Amazon e orçamento para histórico. No v1 o Telegram **não** é fonte: grupos que compram antes de publicar são concorrentes. A latência iguala-se na origem (Pelando JSON + Shopee Affiliate).

---

## 1. Visão

```
 ┌─────────────┐  ┌─────────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐
 │ Shopee Aff  │  │ Keepa BR    │  │ ML Search│  │ Feeds    │  │ Pelando │
 │ GraphQL     │  │ query/prod  │  │ /items   │  │ Awin/Lom │  │ recents │
 └──────┬──────┘  └──────┬──────┘  └────┬─────┘  └────┬─────┘  └────┬────┘
        │                │               │             │             │
        └────────────────┴───────────────┴─────────────┴─────────────┘
                                      │
                              Ingestão + fila
                                      │
                    ┌─────────────────┴──────────────────┐
                    │  Normalização / identidade         │
                    │  (marketplace, native_id, EAN?)    │
                    └─────────────────┬──────────────────┘
                                      │
                    ┌─────────────────┴──────────────────┐
                    │  Observações append-only + stats   │
                    └─────────────────┬──────────────────┘
                                      │
                    ┌─────────────────┴──────────────────┐
                    │  Motor de oportunidade             │
                    │  (P50, min, crowd, freshness)      │
                    └─────────────────┬──────────────────┘
                                      │
                         Confirm live price + affiliate
                                      │
                    ┌────────────┬────┴─────┬────────────┐
                    │  API REST  │ Telegram │  WhatsApp  │
                    │  (núcleo)  │ adapter  │  futuro    │
                    └────────────┴──────────┴────────────┘
```

Keepa **tracking webhook** entra na mesma fila, mas só para ASINs promovidos a watchlist (candidatos quentes ou top sellers).

---

## 2. Componentes lógicos (não são ainda repositórios)

| Componente | Responsabilidade | Baseado em |
|---|---|---|
| Connector Shopee | Poll `productOfferV2` / campanhas | bot-achadinhos + docs oficiais |
| Connector Keepa | `/query` isDeal + `/product` + tracking | docs Keepa; ideias best-buy |
| Connector MLB | Search + item + GTIN | docs ML |
| Connector Feeds | Lomadee/Awin CSV/JSON | docs publisher |
| Connector Pelando | `browse_feed` + `assess` | pelando-mcp (BSD) |
| Identity | Chave nativa; EAN opcional | lacuna L3 |
| History | Série + janelas | schema best-buy reescrito |
| Detector | Score + thresholds config | ADR-09 |
| Confirmer | Preço vivo + link afiliado | ADR-11 |
| Publisher API | `GET /opportunities` | requisito; PromoHubs invertido |
| Publisher Telegram | Push | padrão dos bots |
| Observability | tokens, lag, circuit | Pelando client + Keepa fields |

Um deploy v1 pode ser **um serviço Python** com workers asyncio e Postgres. Não precisa de Kubernetes.

---

## 3. Fluxos

### 3.1 Descoberta contínua

1. Cada conector respeita seu token bucket.
2. Emite `RawOffer` (payload original + hash).
3. Normaliza para `OfferObservation`.
4. Atualiza stats se a identidade já tiver N pontos.
5. Detector emite `OpportunityCandidate` ou descarta com motivo.

### 3.2 Confirmação (obrigatória para publish)

1. Resolve API oficial da loja (Creators GetItems, Shopee itemId, ML item).
2. Recusa se preço divergir além de margem ou se indisponível.
3. Gera afiliado fresco.
4. Grava `Opportunity` imutável com breakdown.

### 3.3 Watchlist Amazon (baixa latência relativa)

1. Detector ou regra promove ASIN.
2. Keepa `tracking add` domain 12, webhook.
3. Evento entra na fila como observação `source=keepa_tracking`.
4. Mesmo confirmer.

---

## 4. Dados (esboço)

Não é schema DDL final.

- `raw_payloads(id, source, fetched_at, body, hash)`
- `observations(id, marketplace, native_id, ean, title, price, price_type, currency, condition, availability, captured_at, source, raw_id)`
- `stats(marketplace, native_id, window_days, n, min, p50, p90, updated_at)`
- `opportunities(id, observation_id, score, breakdown_json, affiliate_url, confirmed_price, status, created_at)`
- `watchlist(marketplace, native_id, reason, keepa_tracking)`

---

## 5. Stack sugerida (não por moda)

| Peça | Escolha | Por quê |
|---|---|---|
| Linguagem | Python 3.12 | pelando-mcp, Keepa lib, httpx async; time-to-adapter |
| HTTP | httpx | comprovado no MCP e no best-buy |
| API | FastAPI | publisher + webhooks Keepa/ML |
| DB | PostgreSQL | JSONB para breakdown/raw; série simples |
| Fila | Postgres `LISTEN` / tabela jobs, ou Redis se necessário | um processo no v1 |
| Scheduler | APScheduler ou cron k8s depois | equivalente honesto ao node-cron |
| Telegram | python-telegram-bot **como adapter** | não como núcleo |
| MCP Pelando | opcional: chamar o servidor BSD ou extrair client | não reinventar o quality |

Node (bot-achadinhos) não justifica um segundo runtime no v1.

---

## 6. O que muda em relação à intuição inicial

Estas descobertas **alteram** um desenho “scrape tudo em tempo real”:

1. **Descoberta em massa já existe em APIs de afiliados e Keepa Product Finder**, não em crawlers.
2. **PA-API morreu**; Amazon oficial = Creators API.
3. **Keepa Deals pode não incluir BR**; Product Finder é o plano A.
4. **“Tempo real” da loja não está disponível**; webhooks Keepa são ~horários.
5. **Percentual da loja é armadilha**; Pelando crowd + histórico são os sinais úteis.
6. **Multi-loja sem EAN é mentira estatística**; v1 intra-loja.
7. **O melhor código Keepa do workspace é privado e europeu** — reimplementar, não fork.
8. **Pelando é ouro como qualidade e veneno como preço** — adapter isolado.
9. **WhatsApp Web não é canal de produto**.
10. **PromoHubs não ensina aquisição** até o backend ser clonado.

---

## 7. Fases pós-aprovação (ainda não executar)

1. Credenciais e spikes autenticados: Keepa domain 12 `/query` e `/product`; Shopee playground; Creators BR; ML search; Lomadee.
2. Esqueleto: Postgres + um conector (Shopee) + detector mínimo + `GET /opportunities`.
3. Keepa histórico Amazon + confirmer Creators.
4. Pelando adapter + ML search.
5. Telegram adapter.
6. Matching EAN e Magalu/Kabum via feed.

---

## 8. Credenciais e informações necessárias para implementar

| Item | Para quê | Obrigatório no v1? |
|---|---|---|
| Shopee Affiliate App ID + Secret (BR) | Descoberta + `offerLink` | Sim, se Shopee entrar no v1 |
| Keepa API key com plano que cubra domain 12 | Histórico e finder Amazon | Sim para Amazon |
| Amazon Associates BR: Credential ID/Secret Creators + `partnerTag` | Preço vivo + afiliado | Sim para Amazon |
| ML App ID/Secret + usuário de teste | Search autenticado se exigido; afiliado TBD | Recomendado |
| Lomadee e/ou Awin publisher | Magalu/Kabum/outros | Se essas lojas forem v1 |
| Telegram bot token | Adapter | Quando houver canal |
| URL pública HTTPS | Webhook Keepa (e ML se usado) | Para tracking |
| Definição de categorias e thresholds | Motor | Sim |
| Posição legal sobre Pelando | Ligar/desligar adapter | Antes de produção |
| Orçamento Keepa (tokens/min) | Dimensionar watchlist | Sim |

Não solicitar secrets neste relatório. Quando a implementação for aprovada, usar `.env` local não versionado.

---

## 9. Critério de pronto para a Fase 1

A Fase 0 encerra aqui. A Fase 1 só deve começar com:

1. Aprovação explícita desta arquitetura (ou de um recorte: ex. “só Shopee+Amazon”).
2. Lista de lojas v1.
3. Credenciais das lojas escolhidas.
4. Confirmação de que **não** se copiará o best-buy-tracker-bot.
