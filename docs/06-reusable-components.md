# 06 — Componentes reutilizáveis

**Data:** 2026-10-01  
**Aviso:** não copiar código de terceiros sem licença compatível.

Classificação:

- **REUTILIZÁVEL** — licença permissiva + qualidade técnica.
- **ADAPTÁVEL** — ideia e trechos úteis; reimplementar.
- **REFERÊNCIA** — conceito válido; código inadequado ou licença bloqueante.
- **DESCARTAR** — obsoleto, inseguro ou sem benefício.

---

## Matriz

### bot-achadinhos — `vinniciusnascimento/bot-achadinhos`

| Informação | Descrição |
|---|---|
| Origem | https://github.com/vinniciusnascimento/bot-achadinhos |
| Funcionalidade | Polling GraphQL Shopee Affiliate → filtro → Sheets → Groq → Telegram |
| Arquivos | `index.js` (único módulo), `package.json` |
| APIs | `open-api.affiliate.shopee.com.br/graphql`, Groq, Telegram, Google Sheets |
| Aquisição | `productOfferV2` por keyword aleatória |
| Atualização | Cron 15 min |
| Histórico | Inexistente |
| Regras | `priceDiscountRate > 20` e `shopType` contém `1`; argmax desconto |
| Afiliados | `offerLink` nativo |
| Dependências | ver `package.json` |
| Licença | **ISC** (`package.json` L5) |
| Segurança | Sem secrets no git; assinatura não-HMAC; Sheets overwrite; envio Telegram com `null` |
| Classe | **ADAPTÁVEL** |

Reaproveitar: contrato GraphQL, lista de campos, ideia de `shopType`/`isKeySeller`.  
Não reaproveitar: monólito, Groq como seletor, desconto da loja como verdade, keyword aleatória por página.

---

### pelando-mcp — `gabrielbelli/pelando-mcp`

| Informação | Descrição |
|---|---|
| Origem | https://github.com/gabrielbelli/pelando-mcp |
| Funcionalidade | Cliente HTTP + MCP tools + qualidade da comunidade |
| Arquivos | `src/pelando_mcp/{client,api,models,quality,normalise,cache,server}.py`, `tools/deals.py`, `tools/common.py` |
| APIs | `api-web.pelando.com.br` (não pública) |
| Aquisição | REST JSON; SSR planejado e ausente |
| Atualização | On-demand; TTL 15 min |
| Histórico | Inexistente como curva |
| Regras | `quality.assess`, `assess_relevance`, `detect_condition` |
| Afiliados | Recusa `redirectUrl` |
| Dependências | mcp, httpx, pydantic, selectolax, structlog — Python ≥ 3.12 |
| Licença | **BSD 2-Clause** (`LICENSE`) |
| Segurança | UA honesto, robots, rate limit, sem secrets |
| Classe | **REUTILIZÁVEL** (módulos client/quality/normalise) |

Condições: manter copyright BSD; tratar a API Pelando como fonte **secundária e instável**; não burlar Cloudflare.

---

### promohubs-frontend — `Victor-Gabriel-Barbosa/promohubs-frontend`

| Informação | Descrição |
|---|---|
| Origem | https://github.com/Victor-Gabriel-Barbosa/promohubs-frontend |
| Funcionalidade | UI Telegram + OCR NF |
| Arquivos | `handlers/*.py`, `services/ocr_service.py`, `config.py`, `main.py` |
| APIs | `{API_URL}/produtos\|cupons\|kabum\|promocoes` |
| Aquisição | HTTP GET lista completa, filtro local |
| Atualização | No clique |
| Histórico | Inexistente neste repo |
| Regras | `publicado`, faixas de preço |
| Afiliados | Link da API, sem rewrite |
| Dependências | pyTelegramBotAPI, OpenCV, Tesseract, RapidFuzz |
| Licença | **MIT** |
| Segurança | Sem timeout; PII de NF |
| Classe | **REFERÊNCIA** (UX). OCR **ADAPTÁVEL** só se NF entrar no escopo |

Backend `BackendPromohubs` não analisado.

---

### best-buy-tracker-bot — `Ithilion90/best-buy-tracker-bot`

| Informação | Descrição |
|---|---|
| Origem | https://github.com/Ithilion90/best-buy-tracker-bot |
| Funcionalidade | Watchlist Amazon + Keepa + scrape + Telegram |
| Arquivos | `src/keepa_client.py`, `price_fetcher.py`, `bot.py`, `db.py`, `resilience.py`, `utils.py`, `sql/02_schema.sql` |
| APIs | Keepa `/product`, Telegram, HTML Amazon |
| Aquisição | ASIN conhecido; sem discovery |
| Atualização | 30 min |
| Histórico | Keepa lifetime + `price_history` |
| Regras | drop > 1 ou > 5%; historical min; ratio 0.2–5.0 |
| Afiliados | `tag=` |
| Dependências | keepa 1.3.15, PTB 21.6, httpx, bs4 |
| Licença | **Privada** (`README.md` L133–135) |
| Segurança | Debug commands; scrape; chave Keepa |
| Classe | **REFERÊNCIA** — **não copiar código** |

Ideias a reimplementar: parser csv Keepa, circuit breaker, schema `price_history` com `source`, validação scrape vs histórico, batch 100 ASINs.

Inadequações BR: sem `com.br`, sem `BRL`, sem `R$` em `parse_price_text` (`utils.py` L39, L149–152).

---

### amazon-price-tracker — `B0ND07/amazon-price-tracker`

| Informação | Descrição |
|---|---|
| Origem | https://github.com/B0ND07/amazon-price-tracker |
| Funcionalidade | Scrape Selenium Amazon IN |
| Arquivos | `main.py`, `telegram_bot.py`, `trackers/amazon_tracker.py`, `product_manager.py` |
| Aquisição | Selenium + headers aleatórios + cookies sintéticos |
| Atualização | 10–20 min + 10–15 s entre itens |
| Histórico | Inexistente |
| Licença | Sem LICENSE; “personal use only” |
| Segurança | `config.env` e `flipkart_cookies.json` versionados; evasão CAPTCHA |
| Classe | **DESCARTAR** |

`ProductManager` atomic JSON write é trivial demais para justificar reuso.

---

### BlueBot — ausente

| Informação | Descrição |
|---|---|
| Origem | https://github.com/SaulloGabryel/BlueBot |
| Funcionalidade declarada | Monitor de grupos + conversão de afiliado + WhatsApp |
| Arquivos (GitHub) | `bot.py`, `Affiliates/*.py`, `Whatsapp/server.ts`, `chromedriver.exe` |
| Licença | MIT no README (2026-10-01) |
| Classe | **REFERÊNCIA** até clone + auditoria. Binário ChromeDriver versionado = risco |

---

## Matching entre lojas

**Indisponível** em todos os clones. Melhores pistas externas:

- Keepa `code=` EAN → ASIN Amazon.
- ML `attributes` GTIN + `catalog_product_id`.
- Título+marca: `assess_relevance` Pelando (BSD) como fallback de baixa confiança.

---

## O que NÃO reutilizar

- Scraping Selenium/httpx de PDP Amazon como fonte primária.
- Redirect Pelando.
- Desconto percentual da loja como único score.
- WhatsApp Web não oficial como canal de produção.
- Qualquer arquivo do best-buy sem autorização (licença privada).
- Cookies e `config.env` do amazon-price-tracker.
