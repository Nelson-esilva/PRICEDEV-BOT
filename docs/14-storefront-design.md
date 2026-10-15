# PromoDev — direção de design da vitrine

Reformulação implementada em `storefront/`, em 8 de outubro de 2026. O dashboard interno em `frontend/` é outro produto.

## Direção

A interface deve ajudar a encontrar, comparar e abrir uma oferta com confiança. A composição usa verde profundo, superfícies claras, tipografia com hierarquia e imagens de produto com espaço próprio. A personalidade aparece no logotipo, na ilustração vetorial do destaque e na linguagem; os controles seguem padrões familiares de catálogo.

Não existe uma topologia ou um espaçamento universalmente correto. As medidas abaixo são as decisões desta implementação, escolhidas para este catálogo e revisadas com seus dados reais.

## Pesquisa e referências

| Referência consultada | O que foi aproveitado |
| --- | --- |
| [Promobit](https://www.promobit.com.br/) | Busca, descoberta por categoria e contexto da loja como partes centrais de uma vitrine de ofertas brasileira. |
| [Pelando](https://www.pelando.com.br/) | Acesso rápido a diferentes formas de explorar ofertas, incluindo recentes e preço. Sem reproduzir recursos sociais que este produto não oferece. |
| [Baymard — listas de produtos e filtros](https://baymard.com/research/ecommerce-product-lists) | Tratar listagem, filtros e ordenação como um único fluxo de descoberta e comparação. |
| [Baymard — interface de filtros](https://baymard.com/blog/ecommerce-filter-ui) | Filtros persistentes no desktop, resumo removível das seleções e painel dedicado no celular. |
| [Nielsen Norman Group — hierarquia visual](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/) | Usar escala, contraste e agrupamento para indicar a ordem de leitura. |
| [W3C — tamanho mínimo dos alvos](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) | Considerar tamanho e separação dos controles. Os principais controles móveis adotam 44 px; não confundir esta escolha com o mínimo de 24 px e suas exceções no critério AA. |

Referências orientam decisões; a identidade, as medidas e a composição foram definidas para o PromoDev. Não foram copiados depoimentos, avaliações, contagens promocionais ou garantias desses sites.

## Arquitetura das páginas

| Rota | Estrutura |
| --- | --- |
| `/` | Busca e navegação → destaque de marca → benefícios → filtros + catálogo → como funciona → rodapé. |
| `/categoria/:category` | Navegação → caminho da página → filtros + resultados da categoria. |
| `/loja/:store` | Navegação → caminho da página → filtros + resultados da loja. |
| `/busca?q=...` | Termo pesquisado → contagem → filtros ativos → ordenação → resultados. |
| `/oferta/:slug` | Caminho da página → imagem + informações e preço → cupom quando disponível → compra na loja → detalhes e retorno ao catálogo. |
| `/privacidade`, `/termos` | Cabeçalho comum → coluna de leitura → rodapé comum. |

O destaque aparece apenas no início do catálogo sem filtros e com ordenação padrão. Busca, categorias e páginas seguintes priorizam os resultados.

A página de oferta abre no próprio site. O botão de compra mantém `/go/{slug}`, abre a loja em nova aba e preserva `rel="noopener sponsored"`.

## Grade e medidas

| Elemento | Desktop | Celular |
| --- | --- | --- |
| Contêiner | Largura fluida, sem teto fixo; 40 px de margem de cada lado em telas amplas | 16 px por lado; 12 px até 360 px |
| Cabeçalho principal | 94 px; logo, busca flexível e ajuda | Logo + ajuda; busca na linha seguinte |
| Navegação por categorias | 49 px; ícone + texto | 46 px; rolagem horizontal própria |
| Coluna dos filtros | 208 px; divisor lateral e 32 px de separação | Painel modal; resumo das seleções junto ao catálogo |
| Grade de ofertas | Colunas automáticas de pelo menos 240 px: 4 em 1.440 px, 6 em 1.920 px e 8 em 2.560 px; 3 até 1.250 px; 2 até 1.000 px | 2 colunas, com 10–12 px de intervalo |
| Intervalo entre cartões | 18 px | 10–12 px |
| Imagem do cartão | Área de 194 px, com `object-fit: contain` | 157 px até 430 px; 140 px até 360 px |
| Conteúdo do cartão | 15 px de respiro lateral | 9–13 px, conforme a largura |
| Cantos | 13 px nos cartões; 20 px no destaque | 13 px nos cartões; 15 px no destaque |
| Controles de filtro e ordenação | Linha acima da grade | Barra que permanece visível durante a rolagem |
| Compra, filtros e paginação móveis | — | Área de toque de pelo menos 44 px de altura |
| Página da oferta | Duas colunas, intervalo de 64 px | Uma coluna: imagem, dados, preço e ação |
| Menu inferior | Oculto | Quatro acessos; respeita a área segura do dispositivo |

Os pontos de adaptação são 1.250, 1.000, 760, 430 e 360 px. O catálogo usa 24 itens por página para limitar o carregamento inicial. A grade mantém duas colunas no celular para permitir comparar produtos com menos rolagem.

O destaque é compacto em telas de até 430 px: o parágrafo de apoio é omitido e a ilustração se reduz, preservando título e ação. Isso antecipa a chegada aos produtos.

## Cores e tipografia

| Papel | Valor | Uso |
| --- | --- | --- |
| Fundo | `#F7F8F5` | Base da página, com menor contraste contra grandes superfícies brancas |
| Superfície | `#FFFFFF` | Produtos, busca e painéis |
| Texto principal | `#24372F` | Títulos e informações centrais |
| Texto secundário | `#5D685E` | Condições, descrições e informações de apoio |
| Verde de ação | `#21634B` | Botões, seleções e marca |
| Verde profundo | `#123E35` | Destaque e preços |
| Verde claro | `#EDF3E9` | Seleções e superfícies auxiliares |
| Lima | `#D9EFA5` | Ênfase sobre fundo escuro |
| Divisórias | `#E2E7DF` | Separação de blocos sem sombras pesadas |

Manrope aparece nos títulos e preços; Inter, nos controles e na leitura corrente. O destaque usa até 44 px no desktop e 31–34 px em celulares estreitos. O título da seção usa 22–27 px; títulos de produto, 14 px no desktop e 12–13 px no celular. O preço usa 25 px nos cartões amplos e 40–43 px na oferta detalhada.

Textos de apoio são menores e secundários. O preço, o nome do produto e a ação têm prioridade. As cores auxiliares foram escurecidas após a verificação de contraste.

## Hierarquia de um cartão

1. Imagem do produto, com selo de desconto apenas quando há dado disponível.
2. Loja de destino.
3. Nome do produto, com acesso aos detalhes.
4. Preço de referência quando disponível e preço atual em destaque.
5. Condição de pagamento pertinente e cupom, quando existentes.
6. Ação “Ver na loja”.
7. Horário relativo de atualização.

O valor de `list_price` vem de uma referência histórica na publicação existente do catálogo. Por isso a interface o chama de “Referência”, sem afirmar que se trata necessariamente do preço anterior cobrado pela loja.

Textos de comissão como “Ganhos extras 22%” não são apresentados como condição de pagamento ou descrição útil ao comprador. O filtro de apresentação não altera os registros de origem.

## Interação e estados

- Busca, loja, categoria, limite de preço, cupom, ordenação e página sobrevivem a recarregamentos por meio da URL.
- Filtros podem ser combinados, removidos individualmente ou limpos em conjunto.
- Menor e maior preço são ordenados no servidor antes da paginação.
- O filtro de cupom ignora valores ausentes, vazios e compostos apenas por espaços.
- O painel móvel mantém alterações em rascunho até “Aplicar filtros”; Escape fecha o painel e o foco retorna ao acionador.
- Cupons são copiados com confirmação acessível; se a área de transferência não estiver disponível, o código continua visível.
- O carregamento usa esqueletos; erro de rede, ausência de ofertas e oferta encerrada têm mensagens e ações distintas.
- Imagens quebradas têm apresentação substituta explícita.
- Foco de teclado, link para pular ao conteúdo, rótulos e anúncios de estado fazem parte dos componentes.
- Animações são desativadas quando o dispositivo prefere movimento reduzido.
- Não há produtos fictícios, contadores de urgência, avaliações ou promessas de menor preço no catálogo.

## Validação

- Compilação de produção com verificação TypeScript.
- 10 testes Python: catálogo, redirecionamento, autenticação pública, filtros combinados, cupons, ordenação, paginação e parâmetros inválidos.
- Fluxos no Chrome automatizado: busca, ordenação, composição de filtros, recarregamento, detalhes, painel móvel, cupom, imagem quebrada e recuperação de falha.
- Verificação de largura em 320, 390, 768, 1.024, 1.440, 1.920, 2.560 e 3.440 px, sem transbordamento horizontal da página.
- Axe com regras WCAG A/AA: sem violações detectadas nos cinco cenários avaliados (catálogo desktop, oferta desktop, painel móvel, catálogo móvel e oferta móvel com cupom/imagem ausente).
- Cenários artificiais de falha e cupom foram interceptados apenas no navegador de testes; não foram gravados no catálogo.

A inspeção automatizada não substitui teste de usabilidade com clientes. A satisfação e a conversão devem ser avaliadas em uso real; não foram medidas nesta entrega.

## Capturas e manutenção

- [Página inicial no desktop](design/promodev-desktop.png)
- [Página inicial em monitor de 2.560 px](design/promodev-wide.png)
- [Página inicial no celular](design/promodev-mobile.png)
- [Catálogo no celular](design/promodev-mobile-catalog.png)
- [Detalhes de uma oferta](design/promodev-detail.png)

A fonte visual está em `storefront/src/styles.css`. Os elementos compartilhados são `Icon`, `ProductImage`, `Coupon` e a marca de `Layout`. A aplicação não ganhou dependências de execução. Chrome/Playwright, Axe e o formatador foram usados a partir de uma instalação temporária em `/tmp`.

Para validar o código:

```bash
cd storefront
npm run build
```

Na raiz do projeto:

```bash
.venv/bin/python -m pytest backend/tests/test_storefront.py backend/tests/test_public_catalog_filters.py -q
```
