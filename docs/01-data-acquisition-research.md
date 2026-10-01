# 01 — Pesquisa de aquisição de dados e descoberta automática

**Data:** 2026-10-01  
**Pergunta central:** como descobrir milhares de oportunidades em várias lojas **sem cadastrar produtos manualmente**?

---

## 1. Resposta direta

É possível, mas **não** varrendo páginas de produto. Os sistemas estudados e as APIs oficiais separam o problema em três famílias:

1. **Catálogos de ofertas já classificadas** (API de afiliados, feeds, deals Keepa, campanhas Shopee).
2. **Agregadores humanos** (Pelando e, analogamente, canais Telegram).
3. **Busca pública paginada** (Mercado Livre `/sites/MLB/search`, Amazon Creators API `searchItems`, Shopee `productOfferV2` por keyword).

Nenhum projeto local combina as três famílias. O desenho viável é um **barramento de conectores**, não um scraper universal.

---

## 2. O que os repositórios realmente fazem

### 2.1 Descoberta por API de afiliados — `bot-achadinhos`

**Comprovado** em `references/github/bot-achadinhos/index.js`:

- Função `callAPIShoppe()` L42–119.
- Endpoint oficial: `POST https://open-api.affiliate.shopee.com.br/graphql`.
- Query GraphQL `productOfferV2(keyword, page, limit)` com `limit: 50` e 10 páginas.
- Keywords fixas L13–34; `sortearNum()` escolhe **uma keyword por página**, não por ciclo.
- Campos: `productName`, `offerLink`, `priceMin`, `priceMax`, `priceDiscountRate`, `shopType`, `commission`.

Throughput teórico por ciclo: 10 × 50 = 500 ofertas brutas, depois filtro. Sem cadastro de SKU.

**Pesquisa complementar (2026-10-01), documentação oficial Shopee Affiliate BR:**  
https://www.affiliateshopee.com.br/documentacao

A API oficial expõe mais do que o bot usa:

| Query | Papel | Confirmação |
|---|---|---|
| `productOfferV2` | Produtos por keyword/loja/itemId, com `offerLink` | Código + docs oficiais |
| `shopeeOfferV2` | Campanhas/coleções Shopee | Docs oficiais |
| `shopOfferV2` | Lojas (key sellers) | Docs oficiais |
| `generateShortLink` | Encurtar URL qualquer em afiliado | Docs oficiais; usado por BlueBot (README) |
| `listItemFeeds` / `getItemFeedData` | Feeds FULL/DELTA de catálogo | Relato de terceiros (Apify actor); **dependência de pesquisa** para confirmar no playground oficial com credencial |

Parâmetros oficiais não usados pelo bot e relevantes: `listType`, `sortType`, `isKeySeller`, `shopId`, `itemId`, `pageInfo.hasNextPage`.

### 2.2 Descoberta por agregador comunitário — `pelando-mcp`

**Comprovado** em `src/pelando_mcp/api.py`:

| Função | Endpoint | Papel |
|---|---|---|
| `browse_feed` L115–152 | `GET /feed/v2/hottest` e `/feed/v2/recents` | Lista o que a comunidade considera quente ou recém-postado |
| `search_deals` L56–112 | `GET /feed/search` | Busca textual; `hideExpired`, `kind=promotion`, `sortOption` |
| `search_stores` L179–183 | `GET /stores/search` | Lojas + cupons |
| `all_stores` L186–190 | `GET /stores/all` | ~300 KB, join table de merchants |

Host: `https://api-web.pelando.com.br` — `models.py` L25.

Isso descobre **ofertas já detectadas por pessoas**, em Magalu, Kabum, Amazon, ML, Terabyte etc., sem SKU prévio. Não cobre o catálogo inteiro de nenhuma loja. Preço = valor digitado pelo usuário (`tools/common.py` L14–17).

Rate limit comprovado: 1 req/s, burst 3 — `client.py` L9–10, L74–91. Cache 15 min no feed.

**Risco:** API interna, Cloudflare, ToS do Pelando. Não é contrato estável.

### 2.3 Descoberta inexistente — trackers Amazon

`best-buy-tracker-bot` e `amazon-price-tracker` **exigem URL/ASIN**.  
`handle_shared_link()` em `bot.py` extrai ASIN de texto; `telegram_bot.py` exige `/add`.  
Não respondem à pergunta da descoberta em massa.

### 2.4 Listagens prontas — PromoHubs

O frontend apenas faz `GET {API_URL}/kabum` e `/promocoes`. A descoberta, se existir, está em `BackendPromohubs`, **ausente** neste workspace. **Dependência de pesquisa.**

### 2.5 Monitoramento de canais — BlueBot (README)

Descoberta = mensagens de grupos Telegram que já contêm links. Alta latência humana, baixa cobertura de catálogo, boa como **fonte oportunista**.

---

## 3. Fontes oficiais fora dos repositórios (Brasil)

Consultadas em 2026-10-01. Nenhuma chamada autenticada foi feita.

### 3.1 Keepa — Amazon.com.br

Documentação: https://keepa.com/api-docs/

| Endpoint | Custo | Serve descoberta? | BR (domain 12) |
|---|---|---|---|
| `/query` Product Finder | ver docs | **Sim**: filtros `isDeal`, `dealType`, preço, categoria | **Confirmado** na tabela oficial de domains |
| `/deal` Browsing Deals | 5 tokens / 150 deals | **Sim**: quedas recentes, até 10.000 ASINs por query | **Não listado** na tabela de `domainId` do `/deal` nesta data (vai só até `11 com.mx`) |
| `/lightningdeal` | 1 ou 500 tokens | Lightning deals | Objeto de deal lista domain 12; a página de request truncou a tabela em alguns locales |
| `/search?type=product` | 10 / página (≤10 itens) | Busca por keyword, volume baixo | Product Request confirma domain 12 |
| `/product` | 1 / ASIN | Não descobre; resolve ASIN/código | **Confirmado** domain 12; parâmetro `code` para EAN/UPC |
| `/tracking` | refill rate | Eventos de ASINs já rastreados | **Confirmado** domain 12 |

**Conclusão:** Keepa é a melhor fonte estruturada de **Amazon BR** para histórico e, via Product Finder, para descoberta. **Não afirmar** que `/deal` funciona no Brasil até teste autenticado: a tabela oficial do endpoint omite `com.br`.

Product Finder exemplo (documentação oficial):

```
GET https://api.keepa.com/query?key=KEY&domain=12&selection=<JSON>
```

Filtros relevantes: `isDeal`, `dealType` (`LIMITED_TIME_DEAL`, `PRIME_DAY`, …), faixas de preço.

### 3.2 Amazon Creators API (sucessora da PA-API 5)

Documentação: https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction  
Locale BR: https://affiliate-program.amazon.com/creatorsapi/docs/en-us/locale-reference/brazil  
Consulta: 2026-10-01. **Confirmado oficialmente.**

- PA-API 5 está **deprecada** (HTTP 403 `AccessDeniedException`).
- Marketplace BR: `www.amazon.com.br`, header `x-marketplace`, moeda `BRL`.
- `POST https://creatorsapi.amazon/catalog/v1/searchItems` — até **10 itens por request**.
- `GetItems` por ASIN; `OffersV2` traz preço do buy box e `DealDetails` / `Price.Savings.Percentage`.
- Não substitui um feed de milhares de deals. Serve para **enriquecer** ASINs já descobertos e gerar link oficial com `partnerTag`.

### 3.3 Mercado Livre (MLB)

Documentação: https://developers.mercadolivre.com.br/pt_br/itens-e-buscas  
Consulta: 2026-10-01. **Confirmado oficialmente.**

| Recurso | Uso para o PriceDevBot |
|---|---|
| `GET /sites/MLB/search` | Busca pública de anúncios ativos (keyword, categoria, filtros). Descoberta sem cadastro |
| `GET /items/{id}` e `/items/bulk` | Detalhe; `ids` antigo entra em descontinuação até 2026-10-25 |
| `/products/search` | Catálogo (produto canônico), não anúncio |
| `/seller-promotions` | **Gestão de promoções do vendedor autenticado**, não varredura do marketplace |
| Tópico `items_prices` | Notificação quando **o preço de um item da aplicação/seller** muda — não é feed global |

Descoberta ML = polling de busca/categorias +, depois, detalhe do item. Eventos em tempo real **não** cobrem o marketplace inteiro para um afiliado/observador.

Atributos úteis no item: `catalog_product_id`, GTIN/EAN em `attributes`, `official_store_id`. Isso é a melhor pista de matching entre lojas encontrada nesta pesquisa.

### 3.4 Magalu

https://developers.magalu.com/docs/apis/products/overview — **API de seller** (SKU/preço/estoque do próprio anunciante), OAuth.  
https://institucional.magaluempresas.com.br/api-gateway-externo — catálogo B2B com onboarding comercial.

**Não** há API pública de “ofertas do Magalu para afiliados” confirmada nesta data. Caminhos reais: Awin/Lomadee (se Magalu estiver no programa), Pelando, ou parceria B2B.

### 3.5 Lomadee

https://docs.lomadee.com.br/api-reference/affiliate/products/all  
`GET https://api-beta.lomadee.com.br/affiliate/products` — paginação, `search`, faixa de preço, `organizationIds`, `isAvailable`.  
**Confirmado na documentação Lomadee** (2026-10-01). Cobre múltiplas lojas parceiras, incluindo potencialmente Magalu/outras, **desde que o publisher tenha acesso**. Catálogo depende do contrato.

### 3.6 Awin

https://success.awin.com/s/article/How-can-I-access-a-Product-Feed  
Feeds CSV/Google Shopping via Create-a-Feed. Atualização típica de feed: horas, não segundos. Útil para lojas BR presentes na Awin (Kabum e outras aparecem em programas de afiliados — **hipótese**, confirmar na conta Awin).

### 3.7 Kabum / Steam

Nenhuma API oficial de ofertas Kabum foi encontrada nesta pesquisa. PromoHubs consome um backend próprio. Steam tem API de promoções da própria loja (`store.steampowered.com`) — **dependência de pesquisa** se o recorte incluir jogos.

---

## 4. Como descobrir milhares de oportunidades — desenho evidenciado

```
                 ┌─ Shopee productOfferV2 / shopeeOfferV2 / feeds
                 ├─ Keepa /query domain=12 (isDeal) [+ /deal se BR for confirmado]
Discovery  ─────┼─ ML /sites/MLB/search por categoria/keyword
  (wide)         ├─ Lomadee / Awin product feeds
                 ├─ Pelando /feed/v2/recents + hottest   (sinal de qualidade)
                 └─ (opcional) canais Telegram já curados

                 ┌─ Keepa /product (ASIN ou code=EAN)
Enrichment ─────┼─ Amazon Creators GetItems + OffersV2
                 ├─ ML /items + attributes (GTIN)
                 └─ Conversão de afiliado (tag, offerLink, generateShortLink)
```

**Não usar** Selenium/httpx contra PDP como motor de descoberta. Os clones que fazem isso só acompanham watchlists pequenas.

---

## 5. Funções e arquivos que implementam descoberta

| Fonte | Arquivo | Função | Linhas |
|---|---|---|---|
| Shopee | `bot-achadinhos/index.js` | `callAPIShoppe` | 42–119 |
| Pelando feed | `pelando-mcp/src/pelando_mcp/api.py` | `browse_feed` | 115–152 |
| Pelando search | idem | `search_deals` | 56–112 |
| Pelando lojas | idem | `search_stores`, `all_stores` | 179–190 |
| Amazon watchlist | `best-buy-tracker-bot/src/bot.py` | `handle_shared_link` | ~387+ |
| Amazon scrape | `best-buy-tracker-bot/src/price_fetcher.py` | `fetch_price_title_image_and_availability` | ~375 |
| Keepa produto | `best-buy-tracker-bot/src/keepa_client.py` | `fetch_lifetime_min_max_current` | 222–249 |
| Kabum UI | `promohubs-frontend/handlers/ofertas_kabum_callbacks.py` | `processar_busca_kabum` | 6–62 |

Nenhum arquivo local chama Keepa `/deal`, `/query`, Creators API, ML search ou Lomadee.

---

## 6. Restrições que mudam a arquitetura

1. **PA-API morreu.** Qualquer desenho “Amazon Associates Search” precisa nascer em Creators API.
2. **Keepa `/deal` pode não incluir BR.** Product Finder é o plano A para Amazon.
3. **ML notifications não são um firehose do marketplace.**
4. **Pelando não verifica preço na loja** e a API é interna.
5. **Desconto percentual da Shopee é o da loja**, frequentemente inflado — ver documento 04.
6. Feeds Awin/Lomadee/Shopee DELTA são o caminho honesto para volume, com latência de minutos a horas, não de segundos.
