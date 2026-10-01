# 10 — Restrições: um afiliado, latência de grupos e custo zero (ou uma assinatura)

**Data:** 2026-10-01  
**Motivo:** revisão da Fase 0 após restrições do produto: evitar vários cadastros de afiliado, não depender da API Amazon (10 vendas/30 dias), espelhar a latência dos grupos de Telegram (≤ 3 min) e evitar plataformas pagas.

Este documento **substitui Keepa + Creators API como núcleo do v1**. A arquitetura de `09-proposed-architecture.md` permanece válida como visão de longo prazo; o recorte abaixo é o que cabe nas restrições.

---

## 1. Completude da análise da pasta

Em `references/github/` existem **exatamente cinco** clones. Todos foram inspecionados de forma estática (código, README, deps, persistência, licença). Nenhum foi executado.

| Repo | Profundidade | Limitação |
|---|---|---|
| `bot-achadinhos` | Integral (`index.js` ~270 linhas) | Único arquivo |
| `pelando-mcp` | Integral nos módulos de aquisição, qualidade, modelos, client | Testes live não rodados |
| `promohubs-frontend` | Handlers e services | Backend de ofertas **não está na pasta** |
| `best-buy-tracker-bot` | Fluxos Keepa, scrape, DB, bot, schema | ~1k linhas; docs de features nem sempre batem com o código |
| `amazon-price-tracker` | Fluxo, tracker Amazon, persistência JSON | Scraper Selenium longo; mercado IN |

**Não estava na pasta:** `SaulloGabryel/BlueBot` (README/GitHub só) e `MessengerPigeonn/amazon-price-monitor` (URL não encontrada).

Isso não muda a conclusão: o único clone local que já é **multi-loja sem cadastro de SKU** é o Pelando.

---

## 2. Descoberta ≠ afiliado

Os grupos de Telegram **não** têm API da Amazon. Eles recebem o que pessoas ou o Pelando já postaram e encaminham o link. A comissão, quando existe, é um passo **depois**.

| Necessidade | Precisa de afiliado Amazon/ML/Magalu? |
|---|---|
| Descobrir a oferta | **Não** |
| Saber se a comunidade acha o desconto real | **Não** (Pelando temperatura) |
| Ganhar comissão Shopee | Sim (você já consegue) |
| Ganhar comissão Magalu/Americanas/Netshoes/etc. | Um cadastro **Lomadee**, não um por loja |
| Ganhar comissão Amazon | Tag Associates **sem API** (opcional); a API das 10 vendas **não é necessária para descobrir nem para colar `?tag=`** |
| Histórico Keepa / preço Amazon oficial | Sim, pago e/ou 10 vendas — **fora do v1** |

---

## 3. Amazon: as 10 vendas bloqueiam a API, não o link

Documentação Creators API (consulta 2026-10-01):  
https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction

> “Have at least 10 qualifying sales within the past 30 days to access the PA API through the Creators API”

**Comprovado em doc oficial:** Creators API herda o mesmo obstáculo da PA-API.

O que **não** exige 10 vendas:

- Postar no Telegram um `sourceUrl` Amazon vindo do Pelando (sem comissão).
- Se no futuro existir tag Associates, acrescentar `?tag=` na URL. Isso é o que o `best-buy-tracker-bot` faz em `with_affiliate` — **não chama** a Product API para gerar o link.

**v1: não usar Amazon API nem Keepa.** Ofertas Amazon entram só via Pelando/Telegram.

---

## 4. O provedor multi-loja que já existe (grátis)

### 4.1 Pelando — melhor match na pasta

- Uma fonte, dezenas de lojas (Amazon, ML, Magalu, Kabum, Shopee, Netshoes, Boticário… evidência nas fixtures e no canal `@pelandobr`).
- Sem cadastro de afiliado para **ler**.
- Código reutilizável BSD: `browse_feed("recents")`.
- Preço digitado por humano; temperatura detecta desconto fake.
- Canal oficial Telegram `@pelandobr` (~55k) **é o Pelando**, não um radar paralelo.

O cache de 15 min em `client.py` L38–40 é do MCP para não martelar a API. Um coletor próprio deve pollar `GET /feed/v2/recents` a cada **30–60 s** (o client já limita 1 req/s), **sem** esse TTL. Esse é o mesmo JSON que o site e os bots de grupos usam (`api-web.pelando.com.br`, `PLAN.md` L48–60). Campos `createdAt` / `firstApprovedAt` marcam a primeira aparição pública (após moderação).

Risco: API interna, Cloudflare, ToS. Isolar atrás de adapter e feature-flag.

### 4.2 Telegram **não** é fonte (decisão do produto)

Grupos que compram antes de publicar são **concorrentes**. Ouvi-los é chegar **depois** do estoque. BlueBot e o recorte anterior de “escutar canais” ficam **fora**.

Há duas espécies de grupo; a fonte a copiar não é o Telegram em nenhum dos casos:

| Tipo de grupo | O que eles fazem | Fonte real | Como empatar |
|---|---|---|---|
| **Repostadores** | Leem Pelando/Promobit e mandam no Telegram | `api-web.pelando.com.br` `/feed/v2/recents` | Pollar esse JSON; chega no mesmo instante que eles, sem atraso de copiar para o canal |
| **Caçadores** | Acham na loja, compram, *depois* postam no Telegram (e às vezes no Pelando) | API/feed da **loja** (Shopee Affiliate, campanhas Lomadee, etc.) | Ir **nessa** API, não no grupo nem no Pelando |

Pelando e Promobit também são comunidades: alguém achou na loja e postou. O feed `recents` é a **primeira superfície pública** (robots.txt bloqueia `/postar`; a fila não aprovada não é pública). Quem scrapeia Pelando para o Telegram não vê a oferta antes desse feed. Quem caça na Shopee **sim** — e o Pelando chega tarde demais para esses casos.

Promobit: mesma lógica comunitária, com **moderação humana obrigatória** (doc oficial de critérios). Não há API estável no workspace; não é o caminho v1.

### 4.3 Shopee Affiliate — fonte de caça, não só monetização

É a única API oficial de **descoberta na loja** já alinhada ao cadastro que você consegue. Query `productOfferV2` / `shopeeOfferV2` com `sortType=1` (LATEST) é o equivalente a estar na mesma origem dos bots de achadinhos Shopee (`bot-achadinhos` usa a mesma GraphQL, mas sorteia keyword em vez de “mais recentes”).

Não cobre Magalu/Amazon/ML. Para essas lojas, sem Keepa e sem API Amazon, a origem pública mais cedo que o Telegram é o **Pelando recents** (empatar com repostadores, não com caçadores da Amazon).

---

## 4.4 Limite honesto

Sem Keepa e sem Creators API, **não há como empatar com um caçador que olha Lightning Deal da Amazon e compra em segundos**. Dá para empatar com quem usa Pelando/Shopee Affiliate — que é a maioria dos grupos de achadinhos genéricos no Brasil.

Você já consegue o cadastro. Serve para **volume Shopee** e `offerLink` oficial. Não cobre Magalu/Amazon/ML. Manter como conector 2, não como única fonte.

---

## 5. Monetização com o mínimo de cadastros

Recomendação v1:

| Cadastro | Custo | Cobre |
|---|---|---|
| Shopee Affiliate (já ok) | Grátis | Só Shopee; `generateShortLink` se o link veio do Pelando |
| **Lomadee** (um) | Grátis, PF, Pix | 300+ marcas; converter URL com `createLinks` / shortener se a loja for anunciante |
| Amazon Associates (opcional, depois) | Grátis | Só `?tag=`, **sem API** |
| Awin | Evitar no v1 | Kabum costuma estar aqui — segundo relato de terceiros; **confirmar** se Kabum está na Lomadee antes de abrir segunda rede |

Lomadee `createLinks` (código de terceiros + docs históricas Buscapé/SocialSoul):  
`GET /service/createLinks/lomadee/{appToken}/?sourceId=...&link1={url}`  
API nova: https://docs.lomadee.com.br — shortener `type=Custom`.  
**Confirmado como documentação/código de terceiros, não testado com credencial.**

Fluxo: Pelando ou Shopee entrega `sourceUrl`/`offerLink` → se host Shopee, shortlink Shopee; senão tenta Lomadee; senão publica link direto sem comissão. Telegram só na **saída**.

Isso evita Magalu Open API, ML afiliado, Awin, Amazon API.

---

## 6. Plataformas pagas — nenhuma é “uma que traz tudo”

| Serviço | Preço (2026-10-01) | Traz tudo? | Cabe na restrição? |
|---|---|---|---|
| Keepa API | a partir de ~€49/mês, **só Amazon**, sem free API | Não | Não como única assinatura útil |
| Keepa Pro site | €29/mês | Só Amazon, sem API de produto decente | Não |
| GeckoAPI | R$ 126,90/mês (10k créditos) | Várias lojas via scrape-as-a-service | Única paga *possível*, mas **não** é feed de promoções; é lookup. ToS das lojas. Latência de deals não documentada como ≤3 min |
| GarimpeAI / PromoSnap | Produto consumidor, coleta ~20 min | Concorrentes, não API para o seu bot | Não |

**Recomendação:** v1 **sem assinatura paga**. Pelando recents + Shopee Affiliate cobrem descoberta. Telegram só na publicação.  
Se no futuro uma assinatura for inevitável: **não** escolher Keepa (Amazon-only). GeckoAPI só se o objetivo virar comparador de SKU conhecido, não radar de achadinhos.

---

## 7. Recorte de arquitetura v1 (sob estas restrições)

```
 Pelando /feed/v2/recents  ─┐
 (mesma API dos bots)      │
                           ├─► fila ─► dedup URL/título ─► quality (temperatura)
 Shopee productOfferV2 /   │                              │
 shopeeOfferV2 LATEST      ─┘                              ▼
                                              score mínimo + filtros
                                                           │
                              ┌────────────────────────────┤
                              ▼                            ▼
                     Shopee generateShortLink      Lomadee createLinks
                              │                            │
                              └────────────┬───────────────┘
                                           ▼
                                 API + Telegram outbound (não é fonte)
```

Fora do v1: ingestão de canais Telegram, Keepa, Creators API, scraping Amazon, Magalu seller API, WhatsApp Web, Awin, BlueBot.

Latência alvo:

- Pelando: poll 30–60 s no `/feed/v2/recents`, sem TTL de 15 min → **igual aos bots que leem o Pelando**, antes de quem só espera o Telegram.
- Shopee: poll da GraphQL oficial (campanhas recentes + keywords) → **igual aos caçadores de Shopee**, não aos grupos que postam depois de comprar.
- SLO: ≤ 1–3 min **após a oferta aparecer no Pelando ou na API Shopee**. Não promete igualdade com caçador Amazon na PDP.

Motor v1: temperatura Pelando + idade (`firstApprovedAt`) + Shopee só como sinal auxiliar. Sem mínimo histórico Keepa até haver série própria.

---

## 8. O que ainda precisa de você

1. Confirmar cadastro Lomadee (um) — ou comissão só Shopee no início.
2. Aprovação para usar a API JSON interna do Pelando (`api-web.pelando.com.br`).
3. **Não** usar canais Telegram como fonte.
4. **Não** gastar tempo nas 10 vendas Amazon para o v1.

Aprovação explícita deste recorte ainda é necessária antes de implementar.
