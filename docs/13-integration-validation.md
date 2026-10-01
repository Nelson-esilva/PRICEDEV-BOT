# 13 — Validação de integrações

**Data:** 2026-10-01

Esta nota registra o que foi conferido contra documentação vigente na implementação, sem chamadas autenticadas a APIs de produção.

## Shopee Affiliate (docs oficiais)

Fonte: https://www.affiliateshopee.com.br/documentacao (consulta 2026-10-01).

| Tópico | Encontrado | Implementado |
|---|---|---|
| Endpoint | `POST https://open-api.affiliate.shopee.com.br/graphql` | Sim |
| Auth | `SHA256 Credential={AppId}, Timestamp={ts}, Signature={sig}` | Sim |
| Signature | `SHA256(AppId + Timestamp + Payload + Secret)` — **não HMAC** | Sim; README do bot-achadinhos estava errado |
| `productOfferV2.sortType` | 1 relevância, 2 vendidos, 3 maior preço, 4 menor preço, 5 comissão | Uso de `sortType=2` (vendidos). **Não há “mais recentes” neste endpoint** |
| `shopeeOfferV2.sortType` | 1 mais recentes, 2 comissão | Consulta de campanhas recentes; campanhas **não** entram no histórico de SKU (sem preço de produto) |
| `generateShortLink` | `mutation { generateShortLink(input: { originUrl, subIds }) { shortLink } }` | Adaptador pronto, só com `ENABLE_SHOPEE` |
| Erros | 10020 assinatura, 10030 rate limit, 10035 sem acesso | Circuit breaker / disable do conector |

**Não testado com credencial real nesta execução.**

## Pelando

- Adapter + fixtures locais.
- `ENABLE_PELANDO=false`. Nenhuma chamada de rede no modo padrão.
- Preço comunitário → `reported_price` apenas; `price_verified=false`.
- `redirectUrl` / `dpl.pelando.com.br` bloqueados em `sanitize_purchase_url`.
- Sem cache de 15 min no coletor de recents.
- Sem bypass de Cloudflare.

**Coleta ao vivo não autorizada neste v1.**

## Lomadee

Stub `createLinks`. Sem prova de contrato atual. Falha → link direto. `ENABLE_LOMADEE=false`.

## Telegram

Somente `sendMessage` de saída. Provisórias não publicam (`ALLOW_PROVISIONAL_AUTO_PUBLISH=false`).

## Divergências documentação Fase 0 vs implementação

1. Hipótese anterior de `productOfferV2 sortType=1 = LATEST` **não** confirma nas docs oficiais BR de 2026-10-01.
2. Assinatura HMAC do README do bot-achadinhos **rejeitada** em favor da concatenação SHA256 oficial.
3. Keepa/Creators/Telegram-fonte continuam fora, conforme documento 10 e prompt mestre.
