import { useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { CATEGORIES, STORE_OPTIONS, discountOf, money, priceCondition, queryString, type HomeData, type List, type PublicDeal } from './api';
import { CouponCode, Empty, Failure, Icon, Loading, TelegramIcon, recentIds, useRemote, useTitle } from './ui';
import { useSite } from './Layout';
import ProductImage from './ProductImage';

// Home em mosaico: campanha grande à esquerda e cartões temáticos com 2×2 produtos.
export default function Home() {
  useTitle('Ofertas, cupons e campanhas'); const state = useRemote<HomeData>('/home'); const data = state.data;
  const telegram = useSite()?.telegram_url || data?.telegram_url;
  if (state.error) return <div className="wide page-space"><Failure error={state.error} retry={state.retry}/></div>;
  if (!data) return <div className="wide page-space"><Loading count={8}/></div>;
  const maxOff = Math.max(0, ...data.discounts.items.map(d => discountOf(d) || 0));
  const rows = distinctRows({ discounts: data.discounts.items, bestsellers: data.bestsellers?.items, loved: data.loved?.items,
    under100: data.under100?.items, premium: data.premium?.items });
  return <div className="wide home-wide">
    {telegram && <a className="telegram-strip" href={telegram} target="_blank" rel="noopener">
      <span className="telegram-strip-icon"><TelegramIcon size={22}/></span>
      <span className="telegram-strip-text"><strong>Grupo de ofertas no Telegram</strong><span>Promoções e cupons no seu celular assim que aparecem. Grátis.</span></span>
      <span className="telegram-strip-button">Entrar no grupo<Icon name="arrow" size={16}/></span>
    </a>}
    <section className="mosaic" aria-label="Destaques">
      <div className="tile tile-campaign">
        <Link to="/campanhas" className="campaign-head"><span>Campanhas das lojas</span><strong>{maxOff ? `Até ${maxOff}% OFF` : 'Ofertas do dia'}</strong></Link>
        <div className="store-pills">{STORE_OPTIONS.map(s => <Link key={s.id} to={`/loja/${s.id}`}>{s.label}</Link>)}</div>
        <div className="campaign-art">{data.discounts.items.slice(0, 4).map(d => <Link key={d.id} to={`/oferta/${d.slug}`} className="art-item" aria-label={d.product}>
          <ProductImage src={d.image_url} name={d.product}/>{discountOf(d) != null && <span className="off-tag">−{discountOf(d)}%</span>}</Link>)}</div>
        <Link to="/campanhas" className="pill-button">Ver campanhas</Link>
      </div>
      {data.trending?.items.length ? <ProductTile tone="hot" kicker={<><Icon name="flame" size={14}/>O que todo mundo procura</>} title="Em alta agora" items={data.trending.items} to="/em-alta" link="Ver tudo em alta" show="off"/>
        : <ProductTile tone="hot" kicker={<><Icon name="flame" size={14}/>Escolhidos pela procura</>} title="Destaques do momento" items={data.featured.items} to="/ofertas" link="Ver destaques" show="off"/>}
      {data.ranking && data.ranking.items.length > 0 && <div className="tile tile-rank">
        <div className="tile-head"><span>Ranking oficial de vendas</span><h2>Mais vendidos em {data.ranking.label}</h2></div>
        <ol className="rank-mini">{data.ranking.items.map(d => <li key={d.id}><Link to={`/oferta/${d.slug}`}>
          <span className="rank-mini-pos">{d.rank_position}º</span><span className="rank-mini-img"><ProductImage src={d.image_url} name={d.product}/></span>
          <span className="rank-mini-text"><span>{d.product}</span><strong>{money(d.current_price)}</strong></span></Link></li>)}</ol>
        <Link className="tile-link" to={`/ranking/${data.ranking.id}`}>Ver ranking completo</Link>
      </div>}
      {data.coupons.items.length > 0 && <div className="tile tile-coupons">
        <div className="tile-head"><span>Copie e use no carrinho</span><h2>Cupons do dia</h2></div>
        <div className="coupon-stack">{data.coupons.items.slice(0, 2).map(c => <div key={c.id} className="coupon-mini">
          <span>{STORE_OPTIONS.find(s => s.id === c.store)?.label || c.store}</span><Link to={`/campanha/${c.slug}`}><strong>{c.title}</strong></Link>{c.code && <CouponCode code={c.code}/>}</div>)}</div>
        <Link className="tile-link" to="/cupons">Ver todos os cupons</Link>
      </div>}
      <ProductTile title="Ofertas no Pix" items={data.pix?.items} to="/ofertas?pix=true" link="Ver ofertas no Pix" show="pix"/>
      <ProductTile title="Achados até R$ 50" items={data.cheap?.items} to="/ofertas?max_price=50" link="Ver achados" show="price"/>
      <ProductTile title="Frete grátis" items={data.free_shipping?.items} to="/ofertas?free_shipping=true" link="Ver com frete grátis" show="ship"/>
    </section>

    <section className="category-cards" aria-label="Comprar por categoria">
      {CATEGORIES.slice(0, 5).map(c => <CategoryCard key={c.id} id={c.id} label={c.label}/>)}
    </section>

    <ProductRow id="descontos" title="Maiores descontos de hoje" items={rows.discounts} to="/maiores-descontos"/>
    <ProductRow id="vendidos" title="Mais vendidos" items={rows.bestsellers} to="/ofertas?sort=best_selling"/>
    <ProductRow id="queridinhos" title="Queridinhos: nota 4,7+ e milhares de vendas" items={rows.loved} to="/ofertas?min_rating=4.7&min_sales=1000"/>
    <RecentRow/>
    <ProductRow id="ate100" title="Achados até R$ 100" items={rows.under100} to="/ofertas?max_price=100"/>
    <ProductRow id="premium" title="Ofertas de alto valor" items={rows.premium} to="/ofertas?min_price=1000&sort=discount"/>
    {!!data.recent?.items.length && <Strip items={data.recent.items}/>}

    {telegram && <TelegramCta href={telegram}/>}
    {!data.featured.items.length && !data.discounts.items.length && <Empty/>}
  </div>;
}

// Cada fileira pula o que já apareceu nas de cima (na ordem da página), para a home não se repetir.
function distinctRows<K extends string>(rows: Record<K, PublicDeal[] | undefined>): Record<K, PublicDeal[]> {
  const seen = new Set<string>(); const out = {} as Record<K, PublicDeal[]>;
  for (const key of Object.keys(rows) as K[]) {
    const fresh = (rows[key] || []).filter(d => !seen.has(d.id)).slice(0, 12);
    fresh.forEach(d => seen.add(d.id)); out[key] = fresh;
  }
  return out;
}

// Fileira de produtos: mostra só os que cabem numa linha (o resto fica no "Ver todos").
function ProductRow({ id, title, items, to }: { id: string; title: string; items?: PublicDeal[]; to?: string }) {
  if (!items?.length) return null;
  return <section className="panel-wide" aria-labelledby={`${id}-titulo`}>
    <div className="panel-head"><h2 id={`${id}-titulo`}>{title}</h2>{to && <Link to={to}>Ver todos</Link>}</div>
    <div className="discount-row">{items.map(d => <Link key={d.id} to={`/oferta/${d.slug}`} className="discount-item">
      <span className="discount-img"><ProductImage src={d.image_url} name={d.product}/>{discountOf(d) != null && <span className="off-pill">{d.price_max ? 'até ' : ''}−{discountOf(d)}%</span>}</span>
      <span className="discount-store">{STORE_OPTIONS.find(s => s.id === d.store)?.label || d.store}</span>
      <span className="discount-name">{d.product}</span>
      {d.list_price ? <s>{money(d.list_price)}</s> : <span className="discount-gap"/>}
      <strong>{d.price_max ? <small>a partir de </small> : null}{money(d.current_price)}{priceCondition(d) && <small> {priceCondition(d)?.when}</small>}</strong></Link>)}</div>
  </section>;
}

// Vistos recentemente: ids guardados no navegador; preço e disponibilidade vêm atualizados da API.
function RecentRow() {
  const [ids] = useState(recentIds);
  const state = useRemote<List<PublicDeal>>(ids.length ? `/deals?${queryString({ ids: ids.join(','), limit: 24 })}` : null);
  const order = new Map(ids.map((id, n) => [id, n]));
  const items = [...(state.data?.items || [])].sort((a, b) => (order.get(a.id) ?? 99) - (order.get(b.id) ?? 99));
  return <ProductRow id="vistos" title="Vistos recentemente" items={items}/>;
}

function ProductTile({ title, kicker, items, to, link, show, tone }: {
  title: string; kicker?: ReactNode; items?: PublicDeal[]; to: string; link: string; show: 'off' | 'pix' | 'price' | 'ship'; tone?: 'hot';
}) {
  if (!items?.length) return null;
  return <div className={`tile tile-products ${tone ? `tile-${tone}` : ''}`}>
    <div className="tile-head">{kicker && <span>{kicker}</span>}<h2>{title}</h2></div>
    <div className="mini-grid">{items.slice(0, 4).map(d => <Link key={d.id} to={`/oferta/${d.slug}`} className="mini-item" aria-label={d.product}>
      <span className="mini-img"><ProductImage src={d.image_url} name={d.product}/></span>
      {show === 'off' ? (discountOf(d) != null ? <span className="off-tag">−{discountOf(d)}%</span> : <strong>{money(d.current_price)}</strong>)
        : show === 'pix' ? <strong>{money(d.current_price)} <small>no Pix</small></strong>
        : show === 'ship' ? <span className="ship-free"><Icon name="truck" size={13}/>Frete grátis</span>
        : <strong>{money(d.current_price)}</strong>}
    </Link>)}</div>
    <Link className="tile-link" to={to}>{link}</Link>
  </div>;
}

const CATEGORY_CAPTIONS: Record<string, string> = {
  eletronicos: 'Fones, smartwatch e áudio', informatica: 'Monitores, SSD e periféricos', celulares: 'Smartphones e acessórios',
  casa: 'Air fryer, panelas e organização', moda: 'Tênis, roupas e bolsas', beleza: 'Perfumes e cuidados', games: 'Consoles, controles e jogos',
};
// Produto "cara da categoria" para a foto do cartão: o mais destacado que é desse tipo.
const CATEGORY_FACES: Record<string, RegExp> = {
  eletronicos: /\b(fone|headphone|smart ?tv|televisor|caixa de som|soundbar|smartwatch|echo|kindle)\b/i,
  informatica: /\b(monitor|notebook|ssd|teclado|mouse|processador|placa)\b/i,
  celulares: /\b(smartphone|celular|iphone|galaxy|redmi|xiaomi|motorola)\b/i,
  casa: /\b(air ?fryer|fritadeira|panela|cafeteira|liquidificador|aspirador|potes?)\b/i,
  moda: /\b(t[eê]nis|camisa|camiseta|cal[cç]a|vestido|bolsa|jaqueta|sand[aá]lia)\b/i,
  beleza: /\b(perfume|creme|shampoo|hidratante|maquiagem|s[eé]rum)\b/i,
  games: /\b(playstation|ps5|xbox|nintendo|console|controle)\b/i,
};
function CategoryCard({ id, label }: { id: string; label: string }) {
  const items = useRemote<List<PublicDeal>>(`/deals?${queryString({ category: id, sort: 'featured', limit: 24 })}`).data?.items || [];
  const face = CATEGORY_FACES[id]; const top = (face && items.find(d => d.image_url && face.test(d.product))) || items.find(d => d.image_url);
  return <Link to={`/categoria/${id}`} className="category-card"><strong>{label}</strong>
    <span className="category-img">{top ? <ProductImage src={top.image_url} name={label}/> : null}</span>
    <span className="category-caption">{CATEGORY_CAPTIONS[id] || 'Ofertas selecionadas'}</span><span className="tile-link">Ver ofertas</span></Link>;
}

function Strip({ items }: { items: PublicDeal[] }) {
  const row = useRef<HTMLDivElement>(null);
  const move = (dir: number) => row.current?.scrollBy({ left: dir * row.current.clientWidth * 0.8, behavior: 'smooth' });
  return <section className="panel-wide strip" aria-labelledby="chegaram-titulo">
    <h2 id="chegaram-titulo">Acabaram de chegar</h2>
    <div className="strip-row"><button className="strip-arrow" aria-label="Anteriores" onClick={() => move(-1)}><Icon name="back" size={18}/></button>
      <div className="strip-items" ref={row}>{items.map(d => <Link key={d.id} to={`/oferta/${d.slug}`} className="strip-item" title={d.product} aria-label={d.product}><ProductImage src={d.image_url} name={d.product}/></Link>)}</div>
      <button className="strip-arrow" aria-label="Próximos" onClick={() => move(1)}><Icon name="chevron" size={18}/></button></div>
  </section>;
}

export function TelegramCta({ href }: { href: string }) {
  const handle = href.replace(/^https?:\/\/(t\.me|telegram\.me)\//, '@').replace(/\/$/, '');
  return <section className="telegram-cta" aria-labelledby="tg-titulo">
    <div className="telegram-text"><span className="telegram-badge"><TelegramIcon size={48}/></span>
      <div><h2 id="tg-titulo">Receba as ofertas antes de todo mundo</h2><p>Entre no grupo do PromoDev no Telegram: promoções, cupons e erros de preço no seu celular, assim que aparecem. Grátis e sem spam.</p></div></div>
    <div className="telegram-actions"><a className="tg-primary" href={href} target="_blank" rel="noopener">Entrar no grupo</a>{handle.startsWith('@') && <a className="tg-secondary" href={href} target="_blank" rel="noopener">{handle}</a>}</div>
  </section>;
}
