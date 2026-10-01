# 07 — Lacunas técnicas

**Data:** 2026-10-01

Cada lacuna: problema, evidência, impacto, alternativas, recomendação, pesquisa extra.

---

## L1. Descoberta multi-loja sem cadastro de SKU

**Problema:** nenhum sistema local cobre Amazon + ML + Shopee + Magalu/Kabum com o mesmo pipeline.  
**Evidência:** inventário (`docs/00-repository-inventory.md`). Pelando é o único multi-loja e depende de humanos + API interna.  
**Impacto:** sem conectores, o produto vira um bot de uma loja só ou um agregador sem histórico.  
**Alternativas:** (a) barramento de fontes oficiais; (b) só Pelando; (c) scrape universal.  
**Recomendação:** (a). Pelando como sinal, nunca como catálogo.  
**Pesquisa:** confirmar Keepa `/deal` em domain 12; feeds Shopee DELTA; quais advertisers Awin/Lomadee BR estão no contrato.

---

## L2. Histórico confiável fora da Amazon

**Problema:** Keepa não cobre Shopee/ML/Magalu. Clones não constroem série.  
**Evidência:** `docs/03-price-history-analysis.md`; bot-achadinhos overwrite Sheets; Pelando sem product id.  
**Impacto:** impossível calcular “abaixo do padrão” e “erro de precificação” nas lojas BR mais relevantes para achadinhos.  
**Alternativas:** construir time series própria; comprar outro data vendor (não identificado para BR); usar só Amazon.  
**Recomendação:** time series própria desde o dia 1, mesmo com janela fria de 14–30 dias. Não lançar alertas de “mínimo histórico” nessas lojas antes de haver N observações.  
**Pesquisa:** vendors BR (Zoom/Buscapé/Precify) — **não confirmados** nesta fase.

---

## L3. Identidade de produto e matching

**Problema:** sem EAN/GTIN/ASIN canônico, variantes e vendedores se misturam.  
**Evidência:** Pelando `normalise.py` (“no brand, model, capacity, SKU, EAN”); Shopee `priceMin`/`priceMax`; best-buy só ASIN.  
**Impacto:** falsos positivos de desconto (128 GB vs 256 GB; novo vs reembalado).  
**Alternativas:** EAN via Keepa `code` + ML attributes; matching fuzzy de título (baixa confiança); não cruzar lojas no v1.  
**Recomendação:** v1 compara **dentro da mesma chave nativa**; v1.1 cluster EAN quando ambos os lados tiverem código. Nunca cruzar só por título sem `assess_relevance`-like.  
**Pesquisa:** campo EAN no `productOfferV2` completo (o bot não pede); Creators `itemInfo.externalIds` no BR.

---

## L4. Latência de segundos não comprovada

**Problema:** expectativa de “menor latência possível” vs realidade horária do Keepa e polling de 15 min.  
**Evidência:** `docs/02-realtime-monitoring-analysis.md`.  
**Impacto:** arquitetura “websocket + scrape contínuo” seria cara e ainda perderia para Keepa/afiliados.  
**Alternativas:** webhook Keepa para watchlist; poll 1–5 min nos feeds de descoberta; aceitar minutos.  
**Recomendação:** SLOs separados (descoberta ≤ 15 min, watchlist ≤ 1 h Keepa, confirmação < 5 s no publish). Não prometer segundos na loja.  
**Pesquisa:** significado de `updateInterval=0` no Keepa; SLA real Shopee feed DELTA.

---

## L5. Dependência de endpoints privados / deprecados

**Problema:** Pelando `api-web` interno; PA-API 5 morta; Magalu Open API é seller-only.  
**Evidência:** `pelando-mcp` PLAN/README; Amazon Creators deprecation notice 2026-10-01; Magalu Devs portfolio seller.  
**Impacto:** quebra silenciosa da descoberta multi-loja se o Pelando mudar; qualquer código PA-API já nasce morto.  
**Alternativas:** só APIs oficiais; Pelando com circuit breaker e fallback.  
**Recomendação:** Creators API desde o início; Pelando isolado atrás de adapter; nunca hardcode GraphQL Pelando (o MCP já mostrou que GraphQL 404).  
**Pesquisa:** ToS Pelando para coleta automatizada.

---

## L6. Rate limits e custo de tokens

**Problema:** clones quase não respeitam cota (Shopee 10 POSTs seguidos; Keepa sem contador de tokens). Pelando é a exceção (1 rps).  
**Evidência:** `index.js` loop sem delay; `keepa_client.py` batch 100 sem checar `tokensLeft`.  
**Impacto:** ban, conta Keepa zerada, 429 Groq (já ocorre).  
**Alternativas:** token bucket genérico (copiar ideia do `PelandoClient`); duas contas Keepa (docs Keepa sugerem separar tracking).  
**Recomendação:** orçamento de tokens por conector; backpressure na fila.  
**Pesquisa:** quotas oficiais Shopee Affiliate e Creators API BR.

---

## L7. Descontos artificiais

**Problema:** `priceDiscountRate` e `discountPercentage` do post não são desconto real.  
**Evidência:** bot-achadinhos L110; Pelando `quality.py` L75–76 (temperatura negativa = desconto fake).  
**Impacto:** o produto vira spam de “70% OFF” inútil.  
**Alternativas:** histórico; crowd; rejeitar merchant %.  
**Recomendação:** merchant % só como feature auxiliar, nunca como gate. Ver `docs/04-discount-detection-analysis.md`.

---

## L8. Preço final inconsistente

**Problema:** cupom, frete, buy box vs 3P, `priceMin` vs variação, preço Pelando não verificado.  
**Evidência:** coupon path morto no amazon-tracker Selenium; best-buy min de vários sellers; Pelando SCOPE_NOTE; Shopee min/max.  
**Impacto:** oportunidade “a R$ X” que checkout mostra Y.  
**Alternativas:** OffersV2 buy box; ML Prices vencedor; confirmar no publish; mostrar faixa min–max honestamente.  
**Recomendação:** persistir `price_type` (buy_box, min_3p, listed, user_posted) e nunca misturar no mesmo score.

---

## L9. Links expirados / afiliado errado

**Problema:** `offerLink` antigo; JWT Pelando; tag Amazon em domínio errado.  
**Evidência:** bot não usa `periodEndTime`; MCP evita JWT; best-buy default domain `amazon.it`.  
**Impacto:** comissão perdida e usuário irritado.  
**Recomendação:** gerar afiliado na hora do publish; validar host; nunca reusar redirect Pelando.

---

## L10. Rastreabilidade

**Problema:** Sheets overwrite; `source` default divergente no best-buy; PromoHubs sem origem visível no frontend.  
**Impacto:** impossível auditar falso positivo.  
**Recomendação:** todo evento de oportunidade carrega `source`, `raw_ref`, `captured_at`, `score_breakdown`, `confirmation_ref`.

---

## L11. Cobertura Amazon Brasil no melhor tracker

**Problema:** o único cliente Keepa do workspace não conhece `com.br`/`BRL`.  
**Evidência:** `keepa_client.py` DomainMap L13–24; `utils.py` `_DOMAIN_CURRENCY` L149–152; grep sem `com.br`.  
**Impacto:** portar o clone “como está” quebraria preços BR (currency default EUR).  
**Recomendação:** reimplementar cliente Keepa com domain 12; não fork do best-buy.

---

## L12. Distribuição por API própria

**Problema:** requisito de API de oportunidades + Telegram/WhatsApp. Clones são bots, não plataformas.  
**Evidência:** nenhum HTTP server de oportunidades; PromoHubs é consumidor.  
**Recomendação:** núcleo = API + fila; canais são adapters. WhatsApp Cloud API no futuro, não `whatsapp-web.js`.

---

## L13. Licenças e risco jurídico

**Problema:** best-buy all rights reserved; amazon-tracker personal use; Pelando API interna; scraping Amazon.  
**Recomendação:** implementação original; BSD só no estilo/algoritmo Pelando quality; afiliados oficiais.

---

## Pesquisa complementar ainda aberta

| Item | Por quê |
|---|---|
| Keepa `/deal` domain 12 | Tabela oficial omite BR |
| `updateInterval=0` Keepa | Latência real |
| Shopee `listItemFeeds` | Volume incremental oficial |
| Creators `externalIds` / EAN no BR | Matching |
| API afiliados MLB (não Selenium) | Comissão ML |
| Advertisers Awin/Lomadee BR | Magalu/Kabum oficiais |
| BackendPromohubs | Como Kabum é obtido |
| ToS Pelando | Legalidade do adapter |
| Quotas Creators API BR | Dimensionamento |
