# PromoDev — Media kit (só Telegram)

Kit visual e textual do **grupo PromoDev** no Telegram. Não cobre site, ops nem Instagram.

## Identidade

| Item | Valor |
| --- | --- |
| Nome do grupo | **PromoDev** |
| Handle / chat de publicação | `PROMODEV` (config `TELEGRAM_PUBLISH_CHAT`) |
| One-liner | Ofertas com link de afiliado, sem enrolação |
| Público | Quem caça preço no BR (Amazon, ML, Shopee e outras lojas) |

## Cores

Alinhadas à vitrine PromoDev:

| Token | Hex | Uso no Telegram |
| --- | --- | --- |
| Laranja | `#F26B21` | Destaque, CTA, avatar |
| Verde | `#1F7A4D` | Preço bom / “POR” |
| Tinta | `#171717` | Texto em artes claras |
| Creme | `#F6F5F2` | Fundo de banner / stories de convite |
| Branco | `#FFFFFF` | Texto sobre laranja/verde |

Evitar roxo, glow neon e estética “dashboard IA”.

## Tipografia (artes)

- Título / marca: sans geométrica forte (ex.: Space Grotesk, Outfit, ou similar)
- Corpo: sans limpa legível em celular
- No post automático do bot a tipografia é a do Telegram (HTML: negrito, sublinhado, riscado)

## Assets

Pasta: [`assets/`](./assets/)

| Arquivo | Formato | Uso |
| --- | --- | --- |
| [`promodev-telegram-avatar.jpg`](./assets/promodev-telegram-avatar.jpg) | 1:1 | Foto do grupo |
| [`promodev-telegram-banner.jpg`](./assets/promodev-telegram-banner.jpg) | 16:9 | Arte de convite / compartilhar o grupo |

**Telegram — foto do grupo:** JPG/PNG quadrado, marca legível em ~40 px.

**Convite:** usar o banner 16:9 + link `t.me/...` do grupo.

## Bio sugerida (descrição do grupo)

Versão curta (~200 caracteres):

```text
Ofertas selecionadas com link de afiliado.
Amazon · Mercado Livre · Shopee e mais.
Preço sujeito a alteração — confira antes de comprar.
```

Versão com regras:

```text
PromoDev — ofertas com afiliado próprio.
Sem spam de cupom vazio. Sem mechan de outros grupos.
Preço pode mudar. Conferir na loja antes de pagar.
```

## Tom de voz

- Direto, em português do Brasil
- Sem clickbait tipo “TORNEIRA DE RICO”
- Sem emojis em excesso fora do template do bot
- Transparência: preço pode mudar; afiliado quando aplicável

## Formato padrão do post (bot)

O publicador já usa este esqueleto — o media kit **não** inventa outro card:

```text
🔥 OFERTA IMPERDÍVEL! 🔥

{título}

💰 De: ~~R$ X~~          ← só se houver preço cheio
💚 POR R$ Y              ← negrito + sublinhado

🎟️ Cupom: …               ← se houver
🛒 Loja: …

🎟️ Resgate os cupons:     ← só se o original trouxer links de cupom
1. …

🔗 Link p/ Compra:
loja/código

⚡ APROVEITE ANTES QUE ACABE!

⚠️ Preço sujeito a alterações…
```

Regras de link:

- Amazon / ML / Shopee → **só** afiliado próprio
- KaBuM, Terabyte, AliExpress etc. → link cru ok, sempre visível
- Mechan de cupom sem produto → não republicar

## Dedup no grupo

Mesmo produto (MLB/ASIN/item Shopee) não republica por **3 horas** (`TELEGRAM_DEDUP_HOURS`). Depois disso, uma promoção nova do mesmo item pode entrar de novo.

## O que não fazer no grupo

- Colar banner/mechan genérico de outros canais como se fosse produto
- Postar link com afiliado de terceiros (Shopee `an_` alheio, etc.)
- Prometer estoque ou preço fixo
- Usar a marca PromoDev em artes com visual roxo/genérico de IA

## Checklist rápido ao atualizar a foto do grupo

1. Exportar avatar 1:1 (PNG)
2. Conferir legibilidade do “PromoDev” em miniatura
3. Atualizar foto no Telegram (admin do grupo)
4. Opcional: fixar mensagem de boas-vindas com a bio + aviso de afiliado

## Aviso legal (fixar ou rodapé de convite)

```text
Alguns links são de programas de afiliados. Podemos receber comissão
sem custo extra para você. Preços e estoque mudam na loja.
```
