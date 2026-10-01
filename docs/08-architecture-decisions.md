# 08 — Decisões de arquitetura (ADRs)

**Data:** 2026-10-01  
**Regra:** decisões só depois da investigação. Nenhuma implementação nestes ADRs.

---

## ADR-01 — Núcleo orientado a eventos, não bot monolítico

**Decisão:** pipeline `connectores → ingestão → identidade → histórico → motor → confirmação → publicação (API/Telegram)`.  
**Evidência:** monólitos `index.js` e `bot.py` misturam I/O, regra e canal; PromoHubs já separa frontend/API e escala melhor como ideia.  
**Alternativas:** um bot Telegram que faz tudo (como os clones); microserviços excessivos.  
**Motivo:** fontes têm latências e contratos diferentes; canais não podem ditar o modelo.  
**Risco:** mais peças no v1. Mitigar com um único processo e filas internas (Redis/Postgres SKIP LOCKED) até haver carga.

---

## ADR-02 — Descoberta por catálogos de ofertas e agregadores, não por scraping de PDP

**Decisão:** conectores oficiais/feeds + Pelando como sinal. Scraping de página de produto **fora** do caminho feliz.  
**Evidência:** amazon-price-tracker (CAPTCHA, cookies, ToS); best-buy scrape só como complemento de watchlist pequena; Shopee/Keepa/ML search já listam milhares sem HTML.  
**Alternativas:** farm de proxies; Creators SearchItems (10 itens — insuficiente como motor único).  
**Motivo:** volume e legalidade.  
**Risco:** Pelando instável; feeds atrasados. Mitigar com várias fontes.

---

## ADR-03 — Amazon BR via Keepa (histórico/deals) + Creators API (preço vivo e afiliado)

**Decisão:** Keepa domain 12 para curva e Product Finder; Creators API para GetItems/OffersV2 e `partnerTag`. PA-API 5 proibida.  
**Evidência:** Keepa docs domain 12; PA-API 403 oficial; best-buy prova o valor do histórico Keepa mas não cobre BR e usa scrape.  
**Alternativas:** só scrape; só Creators; só Keepa.  
**Motivo:** Creators não entrega histórico 90d; Keepa não gera comissão Associates; scrape não escala.  
**Risco:** custo Keepa; `/deal` pode não existir no BR (usar `/query` isDeal). Tracking webhook só para ASINs quentes.

---

## ADR-04 — Shopee via Affiliate GraphQL oficial

**Decisão:** `productOfferV2` + `shopeeOfferV2` + `generateShortLink`; investigar feeds DELTA na implementação.  
**Evidência:** bot-achadinhos em produção conceitual; docs https://www.affiliateshopee.com.br/documentacao.  
**Alternativas:** scrape Shopee; só canais Telegram.  
**Motivo:** único clone com descoberta + afiliado oficiais.  
**Risco:** desconto inflado; quota. Mitigar com histórico próprio e `itemId`.

---

## ADR-05 — Mercado Livre via Search + Item APIs; notificações seller não são o firehose

**Decisão:** polling `/sites/MLB/search` e detalhe `/items`; GTIN/`catalog_product_id` para identidade. Não desenhar o sistema em torno de `items_prices`.  
**Evidência:** docs ML 2026-10-01; tópicos de notificação voltados ao seller.  
**Alternativas:** Selenium (BlueBot); ignorar ML.  
**Motivo:** ML é crítico no BR.  
**Risco:** rate limit search; afiliado ML ainda **dependência de pesquisa**. Sem shortlink oficial confirmado, publicar `permalink` e converter quando a API existir.

---

## ADR-06 — Magalu/Kabum via redes de afiliados (Lomadee/Awin) + Pelando, não Magalu Open API

**Decisão:** Open API Magalu é seller-only — fora. Usar feeds de publisher e/ou Pelando.  
**Evidência:** Magalu Devs portfolio seller; Lomadee products API; Awin Create-a-Feed.  
**Alternativas:** scrape Kabum (PromoHubs backend desconhecido — não assumir).  
**Motivo:** alinhamento a afiliados.  
**Risco:** loja pode não estar no programa. Confirmar na conta antes do v1 dessas lojas.

---

## ADR-07 — Pelando como sensor de qualidade e descoberta oportunista, isolado

**Decisão:** adapter BSD-inspirado (`quality.assess`, `browse_feed recents`), cache curto, circuit breaker, sem `redirectUrl`.  
**Evidência:** melhor multi-loja local; SCOPE_NOTE de preço não verificado; Cloudflare.  
**Alternativas:** ignorar Pelando; usá-lo como fonte de verdade.  
**Motivo:** temperatura negativa é o único detector de “desconto fake” já implementado.  
**Risco:** ToS e 403. Feature-flag para desligar.

---

## ADR-08 — Histórico próprio em Postgres (série temporal) + Keepa como vendor Amazon

**Decisão:** tabela de observações append-only com `source`; stats materializadas (min, p50, p90) por janela 7/30/90d.  
**Evidência:** JSON/Sheets sem série falham; schema `price_history` do best-buy é o embrião certo (reimplementar); Keepa não cobre o resto.  
**Alternativas:** só Keepa (amputa Shopee/ML); Timescale no dia 1 vs Postgres vanilla.  
**Motivo:** Postgres basta no v1 (`timestamp` + índices); Timescale se o volume explodir.  
**Risco:** janela fria. Gate de “mínimo histórico” por `sample_count`.

---

## ADR-09 — Motor de score composto; merchant % nunca é gate

**Decisão:** ver fórmula em `docs/04-discount-detection-analysis.md`. Thresholds configuráveis por categoria/fonte.  
**Evidência:** falha do achadinhos; sucesso relativo do min Keepa + crowd reject.  
**Alternativas:** só % loja; só crowd; ML black-box.  
**Motivo:** explicabilidade (API deve devolver `score_breakdown`).  
**Risco:** pesos iniciais errados. Começar conservador.

---

## ADR-10 — Matching: chave nativa no v1, EAN no v1.1

**Decisão:** `OfferKey = (marketplace, native_id)`. Cluster opcional por EAN quando houver dois códigos.  
**Evidência:** ausência total de matching nos clones; Keepa `code` e ML GTIN existem na documentação oficial.  
**Alternativas:** matching de título no v1 (falso positivo).  
**Motivo:** confiança.  
**Risco:** poucas oportunidades “cross-store” no lançamento. Aceitável.

---

## ADR-11 — Afiliado gerado na confirmação, não na descoberta

**Decisão:** passo `confirm_live_price` chama API da loja e só então emite `offer_link`.  
**Evidência:** `periodEndTime` ignorado; JWT Pelando; tag em domínio errado.  
**Alternativas:** reusar link da descoberta (mais rápido, mais podre).  
**Motivo:** preço e comissão corretos no push.  
**Risco:** +1 round trip. Fila outbound absorve.

---

## ADR-12 — Canais são adapters; WhatsApp oficial no futuro

**Decisão:** API REST/JSON primeiro; Telegram depois; WhatsApp Cloud API depois. Rejeitar WhatsApp Web.  
**Evidência:** requisito do produto; BlueBot README (QR, ban risk); PromoHubs como consumidor de API.  
**Alternativas:** Telegram-first como os clones.  
**Motivo:** o núcleo precisa ser consultável.  
**Risco:** Telegram é o canal que os clones já validam — entregá-lo cedo como adapter, não como núcleo.

---

## ADR-13 — Sem fork de código privado ou scrape-evasivo

**Decisão:** implementação original. Pelando quality/normalise só com preservação BSD se houver cópia substancial.  
**Evidência:** best-buy “all rights reserved”; amazon-tracker cookies/CAPTCHA.  
**Motivo:** risco legal e de segurança.

---

## ADR-14 — Observabilidade por conector

**Decisão:** métricas `tokensLeft`, `http_status`, `lag_since_source_update`, `offers_in`, `offers_accepted`, circuit state.  
**Evidência:** best-buy `system_metrics` (ideia); Keepa devolve `tokensLeft`/`refillRate`; Pelando precisa de 403/challenge.  
**Motivo:** a operação vai falhar por cota, não por bug de score.
