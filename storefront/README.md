# PromoDev — vitrine pública

React + TypeScript + Vite. A marca oficial é a arte azul e laranja em
`public/promodev-logo.jpeg`; não substituir pela antiga etiqueta verde.

## Desenvolvimento

Na pasta `storefront`, execute `npm install` e `npm run dev`. Acesse
http://localhost:5174 com a API na porta 8000. Os proxies `/api` e `/go`
já estão configurados. O build de produção é `npm run build`.

## Experiência

Início, ofertas, maiores descontos, categorias, lojas, busca, campanhas,
cupons, detalhes e favoritos. Filtros e paginação ficam na URL. Favoritos
ficam somente neste navegador (`promodev-saved-v1`, até 100 itens).

## Dados e publicação

Produtos: Shopee e Hub Mercado Livre, com afiliado válido e sinal promocional.
Campanhas: Shopee Affiliate e Awin KaBuM!. Cupons: Awin e códigos explicitamente
associados aos produtos. O catálogo KaBuM! em massa e Pelando permanecem fora.

A sincronização de campanhas roda a cada 15 minutos no scheduler, em tarefa
separada. Configurações Awin existentes: `ENABLE_AWIN`, `AWIN_PUBLISHER_ID`,
`AWIN_KABUM_ADVERTISER_ID` e `AWIN_API_TOKEN`. Nenhum token é enviado ao frontend.
A lista pública exige validade vigente e sincronização nas últimas 24 horas.
Uma falha temporária não apaga o último sincronismo bem-sucedido.

Produtos sem evidência de desconto/cupom não entram na vitrine. Comissão não
é desconto. A validade de produtos deriva da última observação, não da hora
da renderização. Campanhas genéricas não são aplicadas a produtos automaticamente.

## Atualização de banco

O startup mantém compatibilidade com os bancos existentes e cria a tabela
`public_promotions` e os campos de desconto/score de `published_deals` de
forma aditiva. A revisão Alembic `0002_public_discovery` registra a mesma
alteração e aceita banco já atualizado pelo startup. Slugs existentes permanecem.
Para implantação por Alembic, execute `alembic upgrade head` em `backend/`
com o ambiente Python ativo. A migração usa o mesmo `DATABASE_URL` da aplicação.
Não executar downgrade em produção sem backup.

## Referências de UX

Promobit e Slickdeals: descoberta por ofertas, lojas e categorias. Baymard:
filtros combináveis e resumo das seleções. W3C: navegação por teclado, foco,
contraste e movimento reduzido. A implementação usa CSS para as animações,
sem biblioteca adicional, sem autoplay e sem números promocionais fictícios.
