# 04 — Motor de detecção de descontos e oportunidades

**Data:** 2026-10-01

---

## 1. Conclusão

Os algoritmos **comprovadamente implementados** são simples:

1. Percentual informado pela loja acima de um limiar (Shopee > 20%).
2. Preço atual ≤ preço-alvo cadastrado pelo usuário.
3. Queda absoluta/percentual vs último check + mínimo Keepa.
4. Veredito de comunidade (temperatura Pelando), que **não mede desconto real**.

Não existe, em nenhum clone, um motor que junte “percentual configurável de aceitação + desvio da mediana histórica + qualidade + disponibilidade + deduplicação entre lojas”. Isso terá de ser desenhado; as peças úteis são regras isoladas.

---

## 2. Algoritmos encontrados

### 2.1 Argmax de `priceDiscountRate` — bot-achadinhos

```109:114:references/github/bot-achadinhos/index.js
            if (
                produto.priceDiscountRate > 20 &&
                produto.shopType.includes(1)
            ) {
                products.push(produto)
            }
```

Escolha final L250–252: maior `priceDiscountRate` do lote.

**Problema estrutural:** o percentual vem da loja. É o mecanismo clássico de “desconto artificial” (preço de → por inflado). O bot **não consulta histórico**. Comissão existe no payload e é **escondida** da mensagem (prompt L203), mas não entra no score.

Filtro `shopType.includes(1)` = heurística de loja oficial. Sem validação de estoque além do que a API devolver.

Classificação: **comprovado e insuficiente**.

### 2.2 Preço-alvo manual — amazon-price-tracker

`tracker_manager.py` L157–163: `current_price <= target_price`.  
O usuário é o motor. Não escala para descoberta.

### 2.3 Queda vs último preço + mínimo Keepa — best-buy-tracker-bot

Refresh `bot.py` L321–324:

```
drop = old_price - current_price
if drop > 1.0 or (old_price > 0 and drop / old_price > 0.05)
```

Limiares **hardcoded** (1 unidade monetária ou 5%). Não são o “percentual configurável de aceitação” desejado, mas o padrão é o mesmo.

Qualidade de dado:

- Descarta scrape se moeda ≠ domínio — L250–262.
- Descarta scrape se ratio vs Keepa current ∉ [0.2, 5.0] — L264–287.
- `validate_price_consistency()` ajusta min/max vs current — L68–86.
- Pula `unavailable` — L121–123, L313–314.
- `is_historical_min` se preço ≈ min Keepa — L133.

Deduplicação: `(user, asin, domain)` na inserção. Sem dedup entre vendedores do mesmo ASIN na notificação; o scrape escolhe **preço mínimo entre sellers** (`price_fetcher.py`).

Classificação: **comprovado e o mais próximo de “oportunidade real”**, limitado a Amazon não-BR no código.

### 2.4 Crowdsourcing — pelando-mcp `quality.assess`

`src/pelando_mcp/quality.py`:

| Sinal | Limiar | Efeito |
|---|---|---|
| `temperature < 0` | — | `crowd_rejected` |
| `haha > like` | — | `crowd_rejected` (desconto fake / listing enganoso, segundo o próprio comentário L75–76) |
| `temperature >= 300` e não expirado | `HOT_TEMPERATURE` L28 | `crowd_approved` |
| `temperature < 50` e 0 comentários | `QUIET_TEMPERATURE` L31 | `insufficient_signal` |
| idade > 7 dias ainda “active” | `STALE_DAYS` L34 | warning: status não é verificado na loja |
| condição no título (reembalado etc.) | `detect_condition` | warning para não comparar com novo |

Filtros da tool `search_deals`: `min_temperature`, `max_price`, `free_shipping_only`, substring de loja.

Relevância de busca: `assess_relevance` em `normalise.py` L158–205 — tokens de capacidade/variante (Pro, Ti, Max) e acessórios. Score ≥ 0.6.

Isso **detecta descontos mentirosos melhor do que o percentual da loja**, mas não calcula desconto real.

### 2.5 Filtros de faixa de preço — PromoHubs

Kabum: `0–100`, `100–500`, `500+` — `ofertas_kabum_callbacks.py` L23–33.  
Campo `desconto` é exibido se vier da API; origem do cálculo **desconhecida** (backend ausente).  
Filtro `publicado: true`.

### 2.6 Documentado e não ligado

- Dual-mode new/used (`FEATURE_DUAL_MODE_PRICES.md`, `migrate_dual_prices.py`) — funções não estão em `db.py`/`bot.py` atuais.
- Toggle NEW ONLY removido (`REMOVE_NEW_ONLY_FEATURE.md`); Keepa refresh usa `new_only=False`.
- Anomaly Keepa NEW&lt;ALL — MD de fix, código de validação ausente no bot.

---

## 3. Técnicas vs. objetivo do PriceDevBot

| Requisito | Evidência | Adequação |
|---|---|---|
| Percentual configurável de aceitação | Hardcodes 20% / 5% / 1€ | Adaptar: parâmetro por fonte/categoria, não constante |
| Desvio da média/mediana histórica | Keepa stats existem; bots usam min/max, não P50 | Implementar P50/P20 em janela 30/90d |
| Menor preço do período | Keepa min + flag historical min | Reutilizar conceitualmente |
| Anomalia / erro de precificação | Ratio scrape/Keepa; temperatura negativa Pelando | Combinar: outlier vs P50 **e** crowd reject |
| Qualidade dos dados | Circuit breaker, currency check, condition no título | Obrigatório |
| Atualidade | Pelando STALE_DAYS; Keepa last update ~1 h | TTL por fonte |
| Disponibilidade | scrape availability; ML status; Shopee não checa no bot | Confirmar **na publicação** |
| Deduplicação | ASIN+user; Sheets sem dedup; Pelando por post id | Chave nativa + cluster EAN |
| Categoria | Comunidades Pelando; searchIndex Amazon; categoria ML | Filtro na descoberta, não só no display |
| Relevância | `assess_relevance` Pelando | Reutilizar ideia de variantes |

---

## 4. Proposta de scoring (ainda não implementar)

Score composto, todas as entradas rastreáveis:

```
opportunity_score =
  w1 * discount_vs_p50          # (p50 - price) / p50
+ w2 * discount_vs_window_min   # proximidade do mínimo 30d
+ w3 * crowd_bonus              # se veio do Pelando e verdict=approved
− w4 * crowd_penalty            # rejected / haha
− w5 * stale_penalty
− w6 * condition_penalty        # used/repacked
− w7 * unconfirmed_price        # preço só de post, não de API da loja
```

Regras de corte (aceitação configurável):

- Publicar só se `discount_vs_p50 >= threshold[category]` **ou** `price <= window_min * (1+epsilon)` (erro de precificação / mínimo histórico).
- Nunca publicar só com `merchant_discount_pct` (lição do bot-achadinhos).
- Exigir `price_source in {keepa, creators, mlb_item, shopee_offer, feed}` para o preço usado no score; Pelando sozinho gera **candidato**, não oportunidade final.

Isso é **hipótese de arquitetura** fundamentada nas falhas observadas, não código existente.

---

## 5. Erros de precificação

Nenhum clone detecta “preço errado” além de:

- mínimo histórico Keepa (pode ser saldo legítimo);
- temperatura negativa (comunidade acha fake);
- scrape absurdo vs Keepa (erro de parser, não da loja).

Detecção de erro de precificação real (um dígito a menos, listagem no SKU errado) exige:

- comparação com P50 da **mesma identidade** (EAN/ASIN);
- exclusão de usado/reembalado;
- confirmação na API oficial no segundo 0 da publicação.

Sem identidade estável, o sistema vai alertar variações (128 vs 256 GB) como pechincha — exatamente o que `assess_relevance` do Pelando tenta evitar.
