# 05 — Integração de afiliados e links de compra

**Data:** 2026-10-01

---

## 1. Conclusão

Há dois padrões oficiais comprovados ou documentados e vários padrões frágeis:

| Padrão | Oficial? | Onde |
|---|---|---|
| API devolve `offerLink` já tagged | Sim | Shopee `productOfferV2` |
| Acrescentar `tag=` / `partnerTag` na URL Amazon | Sim (Associates) | best-buy `with_affiliate`; Creators API |
| `generateShortLink` Shopee a partir de URL crua | Sim (docs Shopee) | BlueBot README; não está no bot-achadinhos |
| Selenium no site de afiliados ML | Não documentado como API | BlueBot README |
| Redirect JWT Pelando `dpl.pelando.com.br` | Tracker de terceiros | Fixtures Pelando; **código MCP recusa usar** |
| Link cru do backend PromoHubs | Desconhecido | Frontend não reescreve |

Validação de “a oferta continua no ar” **quase não existe**. O best-buy pulsa disponibilidade no scrape; o achadinhos envia o `offerLink` sem HEAD/GET posterior.

---

## 2. Shopee — integração oficial

**Comprovado** em `bot-achadinhos/index.js` L45–94 e confirmado em https://www.affiliateshopee.com.br/documentacao (2026-10-01).

- Endpoint: `https://open-api.affiliate.shopee.com.br/graphql`
- Auth: header  
  `Authorization: SHA256 Credential={APP_ID},Timestamp={ts},Signature={sig}`
- Assinatura **no código:** `SHA256(APP_ID + timestamp + payload + SECRET)` — L77–80.  
  README chama de HMAC — **divergência**. A doc oficial do playground deve ser a autoridade na implementação futura; não copiar o hash cegamente sem conferir o playground.
- Campo `offerLink`: link de afiliado. `productLink` / `originalLink` existem na doc e não são usados pelo bot.
- Conversão de URL arbitrária: mutation/query `generateShortLink` (docs). Necessária quando a descoberta vier do Pelando ou de um canal e o destino for Shopee.

Credenciais: `APP_ID_SHOPPE`, `SECRET_SHOPPE`.

---

## 3. Amazon — tag Associates vs Creators API

### 3.1 Tag na query string — best-buy

```76:93:references/github/best-buy-tracker-bot/src/utils.py
def with_affiliate(url: str, use_offer_listing: bool = False) -> str:
    ...
    tag = (config.affiliate_tag or "").strip()
    ...
            qs["tag"] = tag
```

`build_product_url` L99–131 monta `https://{domain}/gp/product/{asin}?tag=...&ref=nosim`.

`FEATURE_AFFILIATE_LINKS.md` recomenda `/dp/`; o código usa `/gp/product/`. Amazon redireciona. Preserva query existente via `parse_qsl`.

Domínio BR: `_DOMAIN_CURRENCY` em `utils.py` L149–152 cobre it/de/fr/es/co.uk/com/ca/com.mx/co.jp/in. **Não há `amazon.com.br` nem `BRL`.** Default de `domain_to_currency` é `'EUR'` (L156–158). Portar o padrão sem correção precificaria o Brasil em euro.

Licença privada: **não copiar** o arquivo; reimplementar o padrão `tag=` com mapa BR explícito (`amazon.com.br` → `BRL`).

### 3.2 Creators API — oficial, não usada nos clones

https://affiliate-program.amazon.com/creatorsapi/docs/en-us/migrating-to-creatorsapi-from-paapi  
OAuth 2.0, `partnerTag`, marketplace `www.amazon.com.br`.  
`SearchItems` / `GetItems` devolvem links de afiliado corretos para o Associates BR.

PA-API 5: **indisponível** (403).

### 3.3 amazon-price-tracker

README: “Not affiliated with Amazon”. Sem tag.

---

## 4. Pelando — não usar o redirect

`models.py` L174–175: `redirectUrl` é JWT em `dpl.pelando.com.br`, regenerado a cada request. O MCP serializa `sourceUrl` da loja (`tools/common.py` L35, L53).

Para o PriceDevBot: pegar `sourceUrl`, identificar o merchant, **converter com a API oficial daquele merchant**. Não republicar o tracker do Pelando (ToS, expiração JWT, falta de controle da comissão).

Fixtures (`tests/fixtures/stores_search_*.json`) mostram `sourceUrl` Kabum, Magalu, Amazon, ML.

---

## 5. Mercado Livre

BlueBot README: conversão via **Selenium** + clipboard. Isso não é a API oficial de afiliados ML.

Pesquisa complementar: o programa de afiliados do Mercado Livre existe (mercadopago/meli), mas **não foi encontrada nesta sessão uma API pública estável de shortlink comparável à Shopee** com exemplo reproduzível. **Dependência de pesquisa** com conta de afiliado MLB.

Até lá: tratar ML como `sourceUrl` + pesquisa da API de afiliados ML; **não** adotar Selenium como desenho.

Notificações e Prices API são de seller, irrelevantes para gerar comissão de observador.

---

## 6. AliExpress, Lomadee, Awin

- AliExpress: BlueBot README cita API oficial (`ALIEXPRESS_APP_KEY/SECRET/TRACKING_ID`). Ausente localmente.
- Lomadee: product API devolve produtos de lojas parceiras; o contrato de deep link/afiliado está na mesma plataforma — **docs** https://docs.lomadee.com.br (2026-10-01).
- Awin: feeds + Product Finder; link de publisher padrão Awin.

Esses programas são o caminho **oficial multi-loja** para Magalu/Kabum/outras, se as lojas estiverem ativas na conta.

---

## 7. Validação de URL e disponibilidade

| Check | Implementado? |
|---|---|
| Normalizar Amazon `/dp/{ASIN}` | best-buy `normalize_amazon_url`; amazon-tracker `_extract_asin` |
| Expandir short links `amzn.to` | best-buy `SHORT_AMAZON_DOMAINS` L134 |
| Preservar query params | `with_affiliate` sim |
| HEAD/GET de oferta viva antes do push | **Não** nos clones de divulgação |
| Expiração JWT Pelando | MCP evita o problema ao não usar |
| Groq 429 ainda envia mensagem `null` | bot-achadinhos L223–259 — bug de qualidade, não de URL |

Recomendação: fila outbound só após `confirm_live_price()` na API da loja. Link afiliado gerado **no momento da confirmação**, não no momento da descoberta (ofertas Shopee têm `periodStartTime`/`periodEndTime` na doc oficial — o bot local ignora).

---

## 8. WhatsApp / Telegram

- Telegram: todos os bots locais (exceto pelando-mcp) já enviam mensagem com o link.
- WhatsApp: só BlueBot (`whatsapp-web.js` + QR). Não oficial Business API. Risco de ban, sessão frágil. Para o futuro do PriceDevBot, preferir **WhatsApp Cloud API** (oficial) em vez de WhatsApp Web.

Nenhum clone expõe uma **API HTTP de oportunidades**; PromoHubs é o inverso (bot consome API). O requisito “distribuir por API e, futuramente, Telegram e WhatsApp” não está resolvido: precisa de um publisher próprio.
