# PromoDev — Media kit (só Telegram)

Identidade oficial PromoDev e orientações do grupo no Telegram. A mesma logo é aplicada à vitrine pública.

## Identidade

| Item | Valor |
| --- | --- |
| Nome do grupo | **PromoDev** |
| Handle / chat de publicação | `PROMODEV` (config `TELEGRAM_PUBLISH_CHAT`) |
| One-liner | Ofertas com link de afiliado, sem enrolação |
| Público | Quem caça preço no BR (Amazon, ML, Shopee e outras lojas) |

## Logo oficial

Referência aprovada: [logo azul e laranja](assets/4f6c32e6-bd02-4666-b89b-3b5d4917d733.jpeg).
A etiqueta azul com símbolo de código e o nome PromoDev em azul e laranja são
a identidade oficial. Preservar proporções, cores e a arte. Os antigos arquivos
`promodev-telegram-avatar.jpg` e `promodev-telegram-banner.jpg` foram retirados e
não devem ser usados como referência. A cópia usada pelo site fica em
`storefront/public/promodev-logo.jpeg`.

## Cores

Azul e laranja da marca orientam a identidade. Tokens de interface da vitrine:

- Azul de ação: `#0757DC`.
- Azul profundo: `#082956`.
- Laranja: `#F66A0A`.
- Texto: `#15243D`.
- Fundo claro: `#F7F8FB`.
- Branco: `#FFFFFF`.

Estes tokens são complementos para a interface; a arte original não é recolorida.
Evitar a antiga marca verde, roxo, glow neon e estética de dashboard.

## Tipografia

Manrope para títulos e preços; DM Sans para navegação e texto. No Telegram,
a tipografia é a do aplicativo.

## Assets

O JPEG oficial é a fonte de marca disponível. Não há banner oficial aprovado
nesta pasta. Um novo banner deve derivar da identidade acima e não inventar
outra logo. A troca da foto de grupo ou publicação de artes exige uma ação
explícita do administrador; corrigir o media-kit não publica nada no Telegram.

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
- KaBuM! → conversão para afiliado próprio Awin; preservar o rastreamento
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
