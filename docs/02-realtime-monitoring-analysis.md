# 02 — Frequência, latência e monitoramento

**Data:** 2026-10-01  
**Regra:** nenhuma afirmação de “tempo real” sem evidência.

---

## 1. Conclusão

A menor latência **comprovada no código local** é da ordem de **15 minutos** (Shopee) e **30 minutos** (Amazon Keepa+scrape).

A menor latência **documentada oficialmente** para mudança de preço Amazon, sem scraping, é o Keepa Tracking: `updateInterval` em **horas** (valores 0–25), com a documentação afirmando que `1` não dispara exatamente a cada 60 minutos, apenas “o mais próximo possível”. Entrega via **webhook HTTP POST**. Isso é *near-hourly*, não *sub-segundo*.

Nenhum projeto estudado recebe ofertas “em segundos” a partir da loja. BlueBot descreve “real-time” no sentido de **polling Telethon de mensagens já publicadas**.

---

## 2. Matriz dos repositórios

| Sistema | Mecanismo | Intervalo no código | Latência da origem | Eventos? |
|---|---|---|---|---|
| bot-achadinhos | `node-cron` polling | `*/15 * * * *` — `index.js` L264 | A API de afiliados não publica SLA de atualização de `priceMin` | Não |
| pelando-mcp | Sob demanda + cache | TTL search/feed **15 min** — `client.py` L38–40 | Novos posts aparecem quando a comunidade posta; MCP **não agenda** nada | Não |
| PromoHubs FE | Pull no clique do usuário | Sem scheduler | Backend desconhecido | Não |
| best-buy-tracker-bot | Loop `asyncio.sleep(1800)` | **30 min** — `bot.py` L347–351 | Keepa `/product` refresca se last update > ~1 h (docs Keepa) | **Não usa** `/tracking` |
| amazon-price-tracker | `schedule.every(random.randint(10,20)).minutes` | 10–20 min — `main.py` L467–468 + delay 10–15 s **entre produtos** L411–413 | Página Amazon no momento do scrape | Não |
| BlueBot (README) | Telethon polling | Não medido (ausente localmente) | Latência do grupo fonte | “Tempo real” **descrito**, não medido |

Divergências documentação vs código:

- best-buy README diz “hourly”; código dorme 1800 s. `CHECK_INTERVAL_MINUTES` existe em `config.py` / `.env.example` e **não é usado** no loop.
- amazon-price-tracker README diz 10–15 min; código randomiza 10–20 min.

---

## 3. Keepa: três latências diferentes

Fonte: https://keepa.com/api-docs/product.html, `/tracking.html`, `/tracking-object.html` — 2026-10-01.

### 3.1 Product Request (`/product`)

> “If our last update is older than ~1 hour, it will be automatically refreshed before being delivered.”

Parâmetro `update=N` força refresh se a última atualização for mais velha que N horas. Default efetivo ≈ 1 hora.  
Custo: 1 token/ASIN (+ extras para offers/buybox).

O `best-buy-tracker-bot` chama `/product` com `stats=1800` e `history=1` (`keepa_client.py` L709–715) **a cada 30 min**, mas a origem pode devolver dado de até ~1 h.

### 3.2 Browsing Deals (`/deal`)

> “Our deals only provide products that were updated within the last 12 hours.”

`dateRange=0` = últimas 24 h de variação. Página de 150, 5 tokens.  
**Não é webhook.** É snapshot. Domain 12 **ausente** da tabela do endpoint nesta data.

### 3.3 Tracking + webhook (não usado por nenhum clone)

https://keepa.com/api-docs/tracking.html

- `type=add` cria tracking; `type=webhook` registra URL.
- Keepa faz `POST` JSON; exige HTTP 200; retry após 15 s.
- `updateInterval`: inteiro 0–25 **horas**. Docs: *“A setting of 1 hour won't trigger an update exactly every 60 minutes but as close to that as efficiently possible.”*
- Custo contínuo: Regular Tracking reduz refill em **0.9 token por update por locale**.
- Exemplo oficial: 2000 trackings × 1 h = 30 tokens/min de redução.

Isso **não prova** detecção em segundos. Prova notificação push **depois** que o Keepa atualizar o ASIN, tipicamente na escala de dezenas de minutos a uma hora.

`updateInterval=0` existe na faixa 0–25; o significado exato de 0 **não está detalhado** na página de Tracking Object além de “any integer between 0 and 25”. **Dependência de pesquisa** (teste com chave ou suporte Keepa) antes de prometer latência sub-horária.

---

## 4. Mercado Livre notifications

https://developers.mercadolivre.com.br/en_us/users-addresses/products-receive-notifications — 2026-10-01.

Tópico `items_prices`: “you will receive notifications of the item_id each time the price is created, updated or deleted.”

Isso é o mecanismo oficial mais próximo de evento. **Porém** o modelo de notificações ML está atado à aplicação e aos recursos do usuário/seller (itens publicados, ofertas do vendedor, etc.). Não há evidência de inscrição em “todo o MLB”.

Para o PriceDevBot observador/afiliado, ML permanece **polling de search + GET item**, não um websocket de catálogo.

---

## 5. Pelando

Não há webhook. `browse_feed(recents)` é o mais próximo de “o que acabou de ser postado”.  
Latência = tempo humano de postagem + cache de 15 min se o cliente reutilizar TTL.  
Um coletor próprio deve **ignorar o cache de 15 min** no feed `recents` ou usar TTL curto (1–2 min), respeitando 1 req/s.

Cloudflare bloqueia IPs de datacenter — evidência no README/CI do próprio repo (`Drop the CI live-contract job`). Coleta a partir de VPS barata pode falhar.

---

## 6. Shopee Affiliate

Polling. Sem webhook de preço.  
`shopeeOfferV2` com `sortType=1` (LATEST_DESC) é o melhor palpite para “ofertas novas”, **descrito na doc oficial**, não usado no bot-achadinhos (que sorteia keywords).

Feeds DELTA (`listItemFeeds`) seriam incrementais — **não confirmados em código**; relatados por terceiros.

---

## 7. WebSockets, filas, processamento contínuo

| Padrão | Presente? |
|---|---|
| WebSocket loja → bot | **Indisponível** em todos os clones e nas docs oficiais vistas |
| Fila (Rabbit, SQS, Redis stream) | **Ausente** |
| Webhook Keepa | Documentado; **não implementado** |
| Webhook ML | Documentado para sellers; **não implementado** |
| Polling cron/asyncio | **Comprovado** (Shopee 15 min, Amazon 10–30 min) |
| Multiprocess | amazon-price-tracker `main.py` (tracker + bot) |
| Circuit breaker | best-buy `src/resilience.py` (`keepa_api`, `amazon_scraping`, `database`) |

---

## 8. Modelo de latência recomendado (evidência → arquitetura)

Separar **descoberta** de **acompanhamento**:

| Camada | Frequência honesta | Mecanismo |
|---|---|---|
| Descoberta wide (feeds, search, Pelando recents) | 1–15 min | Polling + fila |
| Enriquecimento (Keepa product, Creators GetItems, ML item) | Sob demanda e batch | Tokens/rate limit |
| Watchlist de ASINs “quentes” | Keepa tracking webhook, interval 1 h (ou 0 após teste) | Evento |
| Confirmação de disponibilidade/preço final | Imediata **antes de publicar** oportunidade | GetItems / item ML / Shopee itemId |
| Distribuição Telegram | Segundos após o motor aceitar | Fila de outbound |

**Não vender “ofertas em segundos na loja”.** Vender “descoberta contínua em minutos + alerta de watchlist na escala Keepa + confirmação no momento da publicação”.

Se um canal Telegram já postar o achado, BlueBot mostra que o **encaminhamento** pode ser quase imediato. Isso não substitui a detecção própria.
