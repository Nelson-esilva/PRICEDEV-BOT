# 03 — Histórico de preços

**Data:** 2026-10-01

---

## 1. Conclusão

Só um clone constrói histórico de verdade: `best-buy-tracker-bot`, e o faz **terceirizando a curva longa para o Keepa** e gravando uma série curta local a cada check.

Os demais usam snapshot, percentual da loja, ou preço postado por usuário. **Nenhum compara catálogos entre lojas.** Nenhum usa mediana móvel. Nenhum trata cupom como série paralela de preço líquido.

Para o mercado brasileiro, Keepa cobre **Amazon.com.br (domain 12)** no Product Request. Não há equivalente Keepa para Shopee, Magalu ou Mercado Livre nos materiais estudados: o histórico dessas lojas terá de ser **construído internamente**.

---

## 2. O que cada projeto armazena

### 2.1 best-buy-tracker-bot — histórico híbrido

**Keepa (curva lifetime):** `fetch_lifetime_min_max_current()` em `src/keepa_client.py` L222–249.

- HTTP: `GET https://api.keepa.com/product?asin=...&stats=1800&history=1` L707–716.
- Parser `_minmax_from_history()` L602–704:
  - Série `data['AMAZON']` ou `csv[0]` (pares timestamp/preço em centavos).
  - Heurística de monotonicidade para não confundir timestamp Keepa com preço.
  - Filtro `0 < v <= 2_000_000` centavos.
  - IQR para outliers se n ≥ 5 (L689–697).
- `_pick_amazon_stat()` L329–431 corrige bug de par `[price, timestamp]`.

**Local (série de checks):** tabela `price_history`:

```39:47:references/github/best-buy-tracker-bot/sql/02_schema.sql
CREATE TABLE IF NOT EXISTS price_history (
    id BIGSERIAL PRIMARY KEY,
    item_id BIGINT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    price DOUBLE PRECISION NOT NULL,
    currency TEXT DEFAULT 'EUR',
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    source TEXT DEFAULT 'keepa',
    availability TEXT
);
```

SQLite em `db.py` L260–270 usa default `'scraping'`. O runtime grava source `'scraping'` no refresh. **Inconsistência SQL vs código.**

Identidade do produto: `(user_id, asin, domain)` — `db.py`. Sem EAN.

Uso no motor: `is_historical_min` se `|new_price - min_price| < 0.01` — `bot.py` L133.

Cupons: não modelados. Variações: ASIN individual; `GetVariations` Amazon não é chamado.

### 2.2 amazon-price-tracker — sem histórico

`Product` em `product_manager.py` guarda `current_price`, `target_price`, `last_updated`.  
README L140: TODO “Save price history to a local database”.

### 2.3 bot-achadinhos — snapshot destrutivo

`inserirLista()` faz `spreadsheets.values.update` em `A2:I` — `index.js` L150–160. Cada ciclo **apaga** o anterior.

### 2.4 pelando-mcp — arquivo de posts, não curva

`include_expired=True` em `search_deals` devolve promoções antigas com `price` + `createdAt`. Não há chave de produto. Dois posts do “mesmo” item são linhas independentes. `PLAN.md` coloca comparador 30/90 dias **fora de escopo**.

Preço `0` é válido (jogo grátis) — `models.py` L12–14, L152–153.

### 2.5 PromoHubs frontend — nenhum

---

## 3. Keepa como serviço de histórico (Amazon BR)

Documentação: https://keepa.com/api-docs/product.html — 2026-10-01. **Oficial.**

- Domain `12` = `com.br`.
- Histórico em arrays `csv` por tipo de preço (Amazon, New, Used, Lightning, Buy Box…).
- Lookup por `code` (EAN/UPC/ISBN) além de ASIN — caminho natural de matching Amazon ↔ outras lojas **depois** de ter o código.
- `stats` agrega min/max/avg em janela (o bot usa `stats=1800` minutos ≈ 30 dias).
- Preços em **centavos da moeda local** (BRL cents no domain 12).

Limitações:

- Só Amazon.
- Token caro se `offers=1` (6 tokens por página de ofertas).
- Anomalias NEW vs ALL documentadas nos MDs do best-buy; o `bot.py` atual **não** chama `validate_keepa_anomaly()` (docs de fix vs código divergem).
- `DomainMap` do clone **omite** BR — qualquer reaproveitamento conceitual precisa acrescentar `"com.br": 12`.

---

## 4. Identificação de produtos

| Sistema | Chave | EAN/GTIN | Variantes |
|---|---|---|---|
| best-buy | ASIN + domain | Não | Um ASIN = uma linha |
| amazon-tracker | UUID + URL | Não | — |
| bot-achadinhos | Nenhum (nome + offerLink) | Não | `priceMin`/`priceMax` misturam variações |
| pelando | UUID do **post**, não do produto | Explicitamente ausente (`normalise.py` cabeçalho) | Título livre |
| ML (docs) | `id` do anúncio; `catalog_product_id`; attributes GTIN | **Sim, na API oficial** | Variações no item |
| Keepa | ASIN; `code` EAN | **Sim** | Parent/child ASIN |
| Creators API | ASIN; `GetVariations` | A verificar no GetItems resources | Oficial |

**Comprovado:** nenhum clone local faz matching cross-store.

---

## 5. Médias, medianas, mínimos, anomalias

| Técnica | Onde |
|---|---|
| Mínimo/máximo lifetime Keepa | best-buy, comprovado |
| Média | Keepa `stats` disponível; **não usada** no bot |
| Mediana | IQR só para filtrar outliers da série Keepa, não como referência de “preço justo” |
| Mínimo histórico local | Flag `is_historical_min` |
| Anomalia scrape vs Keepa | ratio &lt; 0.2 ou &gt; 5.0 descarta scrape — `bot.py` L264–287 |
| Anomalia NEW &lt; ALL | Documentada em `FIX_KEEPA_ANOMALY_B07RW6Z692.md`; **não no bot.py atual** |
| Cupom | Flag `COUPON_ALERT` no amazon-tracker; caminho Selenium ativo **não preenche** cupom |
| Desconto da loja como verdade | bot-achadinhos `priceDiscountRate` — **não é histórico** |

---

## 6. Como obter ou construir históricos confiáveis

### Amazon BR

1. Keepa `/product` (ASIN ou EAN) como fonte primária de curva.
2. Série própria em Postgres/Timescale com `source`, `condition`, `seller`, `price_net`, `collected_at`.
3. Creators API OffersV2 no instante da publicação (preço buy box atual, não história).

### Shopee

Sem Keepa. Construir série a partir de `productOfferV2` (`itemId` + `shopId` + `priceMin`) em cada poll.  
`priceMin`/`priceMax` misturam variações — gravar os dois e, se possível, `itemId` específico.  
Histórico curto no início; mínimo de 14–30 dias antes de alarmes “abaixo do padrão”.

### Mercado Livre

Série própria por `item_id` + preço vencedor da Prices API.  
`catalog_product_id` e GTIN para consolidar anúncios do mesmo produto.  
Não há histórico oficial de 90 dias para observadores.

### Magalu / Kabum / outros

Feeds Lomadee/Awin (preço no feed + timestamp de ingestão) e/ou posts Pelando como **sinal**, nunca como curva canônica.

### Pelando

Usar como detector de oportunidade e como arquivo qualitativo, não como time series de produto.

---

## 7. Modelo de dados mínimo sugerido (consequência da evidência)

Não implementar agora. Registro para o ADR:

- `offer_observation(source, native_id, ean, title, price, currency, condition, captured_at, raw_hash)`
- `product_identity(ean, brand, model, confidence)`
- `price_stats(product_id, window, min, p50, p90, last)` materializado
- `source` obrigatório para rastreabilidade (Keepa, shopee_aff, mlb, pelando, feed_awin…)

Sem `source` o sistema herda o bug do best-buy (SQL diz keepa, runtime grava scraping).
