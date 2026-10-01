# 00 — Inventário dos repositórios de referência

**Data da análise:** 2026-10-01  
**Escopo:** inspeção estática de `./references/github/` + pesquisa complementar de repositórios citados e ausentes.  
**Regra observada:** nenhum script, binário ou dependência foi executado.

Legenda de evidência usada em todos os documentos:

| Marcador | Significado |
|---|---|
| **Comprovado** | Observado no código-fonte versionado |
| **Descrito** | Presente em README/docs, não verificado em runtime |
| **Hipótese** | Inferência técnica, não confirmada |
| **Pesquisa complementar** | Documentação oficial ou repositório externo, consultada em 2026-10-01 |
| **Indisponível** | Recurso ausente, descontinuado ou não listado na documentação oficial atual |

---

## 1. Inventário local

O diretório `./references/github/` contém **cinco** repositórios clonados. Não está vazio.

| Pasta local | Remote Git | HEAD | Data do HEAD |
|---|---|---|---|
| `bot-achadinhos` | `vinniciusnascimento/bot-achadinhos` | `c39ee681` | 2026-07-20 |
| `pelando-mcp` | `gabrielbelli/pelando-mcp` | `33213cc0` | 2026-08-10 |
| `promohubs-frontend` | `Victor-Gabriel-Barbosa/promohubs-frontend` | `0f1f590c` | 2026-08-19 |
| `best-buy-tracker-bot` | `Ithilion90/best-buy-tracker-bot` | `53810a6a` | 2025-10-17 |
| `amazon-price-tracker` | `B0ND07/amazon-price-tracker` | `6ffbdd9b` | 2026-07-30 |

Nenhum desses clones corresponde exatamente a `MessengerPigeonn/amazon-price-monitor`. O clone presente é `B0ND07/amazon-price-tracker`.

---

## 2. Repositórios citados e ausentes

| Citação original | Status no workspace | Observação |
|---|---|---|
| https://github.com/vinniciusnascimento/bot-achadinhos | Presente | Código analisado |
| https://github.com/gabrielbelli/pelando-mcp | Presente | Código analisado |
| https://github.com/SaulloGabryel/BlueBot | **Ausente** | README e árvore inspecionados via GitHub em 2026-10-01; código-fonte **não** foi clonado nem executado |
| https://github.com/MessengerPigeonn/amazon-price-monitor | **Ausente e não localizado** | Busca em 2026-10-01 não encontrou esse repositório; o clone local mais próximo é `B0ND07/amazon-price-tracker` |

**Candidatos a adicionar ao workspace (não clonados nesta fase):**

1. `SaulloGabryel/BlueBot` — conversão de links já publicados em grupos Telegram/WhatsApp.  
2. `Victor-Gabriel-Barbosa/BackendPromohubs` — backend que o frontend PromoHubs consome; sem ele a origem das ofertas Kabum/Steam permanece caixa-preta.  
3. Qualquer substituto de `amazon-price-monitor` só deve ser adicionado após confirmação explícita do URL correto.

---

## 3. Fichas por repositório local

### 3.1 `bot-achadinhos`

| Campo | Valor |
|---|---|
| Finalidade real | Bot que varre a API GraphQL de afiliados da Shopee Brasil, filtra desconto e tipo de loja, grava snapshot no Google Sheets, pede texto à Groq e envia **um** produto ao Telegram |
| Linguagem | JavaScript ESM, Node 18+ |
| Dependências | `dotenv`, `googleapis`, `groq-sdk`, `node-cron`, `node-telegram-bot-api` — `package.json` L12–17 |
| Ponto de entrada | `node index.js`; agendador `cron.schedule('*/15 * * * *')` em `index.js` L264–267 |
| Aquisição | `POST https://open-api.affiliate.shopee.com.br/graphql`, operação `productOfferV2` — `index.js` L42–94 |
| Persistência | Google Sheets `A2:I` sobrescrito a cada ciclo — L150–160; sem banco local |
| Histórico | **Indisponível** |
| Afiliados | Campo `offerLink` da API oficial — L54, L141, L199 |
| Licença | ISC — `package.json` L5 |
| Segurança | Sem secrets no código; `.env` e `credentials.json` gitignored. Assinatura SHA256 de concatenação, não HMAC apesar do README |
| Reaproveitamento | **ADAPTÁVEL** (padrão de assinatura e descoberta por keyword); monólito de ~270 linhas |

Fluxo comprovado:

```
cron 15 min → callAPIShoppe() → filtro >20% + shopType 1
           → inserirLista() → argmax(priceDiscountRate)
           → Groq → Telegram
```

### 3.2 `pelando-mcp`

| Campo | Valor |
|---|---|
| Finalidade real | Servidor MCP que lê a API JSON interna do Pelando (`api-web.pelando.com.br`) e anexa veredito da comunidade |
| Linguagem | Python ≥ 3.12 |
| Dependências | `mcp>=2.0`, `httpx`, `pydantic`, `selectolax`, `structlog` — `pyproject.toml` L14–21 |
| Ponto de entrada | `pelando_mcp.server:main` |
| Aquisição | REST não documentado publicamente: `/feed/search`, `/feed/v2/{hottest\|recents}`, `/deals/{id}`, `/stores/search` — `src/pelando_mcp/api.py` |
| Persistência | Cache SQLite HTTP com TTL; **não** histórico de preços |
| Motor | `quality.assess()` — temperatura, reações, idade, condição — `src/pelando_mcp/quality.py` L56–187 |
| Afiliados | **Deliberadamente omitidos**; `redirectUrl` não é modelado — `models.py` L174–175 |
| Licença | BSD 2-Clause — `LICENSE` |
| Segurança | `.env` sem secrets; UA honesto; 1 req/s; robots.txt respeitado |
| Reaproveitamento | **REUTILIZÁVEL** (client, modelos, qualidade, normalização) sob BSD-2 |

**Comprovado:** não é comparador de preços. `tools/common.py` L14–17 declara isso no `SCOPE_NOTE`.

**Descrito e não implementado:** fallback SSR (`PLAN.md`); pasta `parsers/` ausente.

### 3.3 `promohubs-frontend`

| Campo | Valor |
|---|---|
| Finalidade real | Frontend Telegram do PromoHubs: menus, filtros client-side e OCR de nota fiscal |
| Linguagem | Python 3.11+ |
| Dependências | `pyTelegramBotAPI`, `requests`, `opencv-python`, `pytesseract`, `RapidFuzz` |
| Ponto de entrada | `main.py` → `bot.infinity_polling()` |
| Aquisição | `GET {API_URL}/produtos`, `/cupons`, `/kabum`, `/promocoes`; `POST /notas-fiscais` |
| Persistência | Nenhuma local |
| Licença | MIT — `LICENSE` |
| Segurança | Sem timeout nas chamadas `requests.get`; OCR envia texto de NF à API |
| Reaproveitamento | **REFERÊNCIA** de UX Telegram; motor de ofertas está no backend ausente |

### 3.4 `best-buy-tracker-bot`

| Campo | Valor |
|---|---|
| Finalidade real | Watchlist Amazon multi-usuário: link → ASIN → Keepa (min/max/current) + scrape httpx → notificação de queda e mínimo histórico + tag de afiliado |
| Linguagem | Python 3.11+ |
| Dependências | `python-telegram-bot[job-queue]==21.6`, `httpx`, `beautifulsoup4`, `keepa==1.3.15`, `psycopg2-binary` |
| Ponto de entrada | `src/bot.py` `main()` |
| Aquisição | Keepa `https://api.keepa.com/product` + scraping HTML Amazon |
| Persistência | SQLite (`src/db.py`) e schema Postgres `sql/02_schema.sql`; tabela `price_history` |
| Atualização | `asyncio.sleep(1800)` — 30 min hardcoded — `bot.py` L347–351 |
| Afiliados | Query `tag=` — `src/utils.py` `with_affiliate` / `build_product_url` |
| Licença | README: “Private project - all rights reserved” (`README.md` L133–135). **Sem `LICENSE`.** Reuso direto **incompatível** |
| Segurança | Token/Keepa em `.env`; comandos `/debugasin` e `/debugdb`; scraping Amazon |
| Reaproveitamento | **REFERÊNCIA** (licença privada). Ideias: parser Keepa, circuit breaker, validação scrape vs histórico |

**Lacuna crítica para o Brasil:** `DomainMap` em `src/keepa_client.py` L13–24 **não inclui `com.br` (domínio Keepa 12)**. `parse_price_text` em `utils.py` L39 não reconhece `R$`/`BRL`.

### 3.5 `amazon-price-tracker`

| Campo | Valor |
|---|---|
| Finalidade real | Watchlist admin-only Amazon Índia (e Flipkart ainda no código) via Selenium/BeautifulSoup, alerta se preço ≤ alvo |
| Linguagem | Python 3 |
| Dependências | `requests`, `bs4`, `lxml`, `schedule`, `python-telegram-bot==20.7`, `selenium`, `webdriver-manager` |
| Ponto de entrada | `main.py` (multiprocess: tracker + bot) |
| Aquisição | Scraping Selenium Chrome; “API endpoints” são URLs HTML alternativas (`amazon_tracker.py` ~L541–566) |
| Persistência | JSON `data/products.json` — snapshot, sem série temporal |
| Cadastro | Manual `/add <url> <target>` — `telegram_bot.py` |
| Licença | Sem `LICENSE`; README “personal use only” |
| Segurança | `config.env` versionado com URLs de produto; `data/flipkart_cookies.json` contém cookies de sessão; evasão de CAPTCHA |
| Reaproveitamento | **DESCARTAR** para o núcleo; scraping/Selenium contra ToS, mercado IN, sem descoberta automática |

---

## 4. BlueBot (ausente — apenas README/GitHub)

Consulta em 2026-10-01: https://github.com/SaulloGabryel/BlueBot

**Descrito no README (não verificado em código local):**

- Monitora grupos Telegram via Telethon (polling).
- Filtra mensagens com links Shopee, AliExpress e Mercado Livre.
- Converte para link de afiliado: ML via Selenium; Shopee e AliExpress via APIs oficiais.
- Encaminha texto + mídia para Telegram e WhatsApp (`whatsapp-web.js`).
- Licença MIT © 2025 (declarada no README).
- Árvore: `bot.py`, `Affiliates/{shopee,aliexpress,MercadoLivre}_affiliate.py`, `Whatsapp/server.ts`, `chromedriver.exe` binário versionado.

**O que BlueBot não é:** descobridor de catálogo. Ele **repassa oportunidades já publicadas por humanos** em canais. Latência “em segundos” é latência de encaminhamento, não de detecção na loja.

**Risco:** `chromedriver.exe` binário no repositório; Selenium contra Mercado Livre; sessão WhatsApp Web.

Classificação provisória: **REFERÊNCIA** de distribuição e conversão de links; código precisa ser clonado e revisado antes de qualquer reuso.

---

## 5. Mapa de cobertura vs. objetivos do PriceDevBot

| Objetivo | bot-achadinhos | pelando-mcp | PromoHubs FE | best-buy | amazon-tracker | BlueBot (README) |
|---|---|---|---|---|---|---|
| Descoberta sem cadastro | Sim (keywords Shopee) | Sim (feeds Pelando) | Lista pronta do backend | Não (cole link) | Não (`/add`) | Sim, mas de canais Telegram |
| Multi-loja | Não (só Shopee) | Sim (comunidade) | Kabum + Steam + “produtos” | Só Amazon | Amazon IN / Flipkart | ML + Shopee + AliExpress |
| Preço sem scraping | API afiliado | Preço postado (não verificado) | API backend | Keepa + scrape | Só scrape | N/A (não coleta preço) |
| Histórico | Não | Arquivo de posts, sem curva | Backend desconhecido | Keepa + tabela local | Não | Não |
| Desconto real vs histórico | Só `%` da loja | Temperatura da comunidade | Filtro de faixa | Mínimo Keepa | Preço-alvo manual | Não |
| Afiliados | Oficial Shopee | Evita redirect Pelando | Link cru da API | Tag Amazon | Não | Conversão de links |
| Distribuição Telegram | Sim | MCP (não Telegram) | Sim | Sim | Sim | Telegram + WhatsApp |
| API de oportunidades | Não | MCP tools | Consome API alheia | Não | Não | Não |

---

## 6. Conclusões do inventário

1. **Nenhum repositório local implementa o sistema pretendido.** Cada um resolve um recorte.
2. A única descoberta multi-loja sem cadastro de SKU está no **Pelando**, que é agregador comunitário, não catálogo.
3. A única construção séria de histórico está no **best-buy-tracker-bot** via Keepa, mas a licença é privada e o código **não cobre Amazon BR**.
4. A única API oficial de ofertas com link de afiliado já usada no workspace é a **Shopee Affiliate GraphQL**.
5. Scraping (amazon-price-tracker, parte do best-buy) é frágil, viola ToS e não escala para “milhares de oportunidades”.
6. Latência de segundos **não está comprovada** em nenhum clone local. O mais rápido comprovado é polling de 15 min (Shopee) e 30 min (Keepa+scrape).

Documentos seguintes detalham aquisição, latência, histórico, motor, afiliados, reuso, lacunas, ADRs e arquitetura proposta.
