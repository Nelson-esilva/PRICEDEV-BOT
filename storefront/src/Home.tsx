import { Link } from 'react-router-dom';
import { CATEGORIES, STORE_OPTIONS, dateLabel, hasDeadline, queryString, storeLabel, type HomeData, type List, type Promotion, type Ranking } from './api';
import { CouponCode, Empty, Failure, Icon, Loading, SectionHeading, StoreTag, useRemote, useTitle } from './ui';
import DealCard from './DealCard';
import { BannerRotator, CampaignSlide, Carousel, PromotionCard, isBanner } from './Promotions';
import { RankingCard } from './Rankings';

export default function Home() {
  useTitle('Ofertas, cupons e campanhas'); const state = useRemote<HomeData>('/home');
  const data = state.data; const hero = data?.campaigns.items[0]; const coupon = data?.coupons.items[0];
  const campaigns = (useRemote<List<Promotion>>(`/promotions?${queryString({ kind: 'campaign', limit: 24 })}`).data?.items || []).filter(p => !isBanner(p));
  const banners = (useRemote<List<Promotion>>(`/promotions?${queryString({ kind: 'campaign', store: 'mercadolivre', limit: 12 })}`).data?.items || []).filter(isBanner); const coupons = data?.coupons.items.slice(1, 4) || [];
  const rankings = useRemote<List<Ranking>>('/rankings').data?.items.slice(0, 8) || [];
  return <div className="container page-space home">
    <section className="home-hero">
      {banners.length > 0 ? <BannerRotator items={banners}/> : <div className="hero-main">{hero ? <span className="hero-tag"><i/>Campanha · {storeLabel(hero.store)}</span> : <span className="hero-tag"><i/>Shopee · Mercado Livre · KaBuM!</span>}
        <h1>{hero ? hero.title : 'Ofertas, campanhas e cupons em um só lugar'}</h1>
        <p>Ofertas das lojas que você já usa, com a origem do desconto à vista. Você compara aqui e compra direto na loja.</p>
        <div className="hero-actions">{hero && <Link className="button light" to={`/campanha/${hero.slug}`}>Ver campanha<Icon name="arrow" size={16}/></Link>}<Link className={`button ${hero ? 'ghost' : 'light'}`} to="/ofertas">Todas as ofertas{!hero && <Icon name="arrow" size={16}/>}</Link></div>
      </div>}
      <div className="hero-side">
        {coupon ? <div className="hero-coupon"><span className="overline">Cupom da vez</span><Link to={`/campanha/${coupon.slug}`}><strong>{coupon.title}</strong></Link><StoreTag store={coupon.store} extra={hasDeadline(coupon.expires_at) ? `até ${dateLabel(coupon.expires_at)}` : undefined}/>{coupon.code && <CouponCode code={coupon.code}/>}</div>
          : <Link className="hero-link" to="/cupons"><span><strong>Cupons</strong><span>Códigos oficiais das lojas</span></span><Icon name="arrow"/></Link>}
        <Link className="hero-link" to="/maiores-descontos"><span><strong>Maiores descontos</strong><span>Ordenados pelo percentual</span></span><Icon name="arrow"/></Link>
      </div>
    </section>
    <nav className="category-chips" aria-label="Categorias">{CATEGORIES.map(c => <Link key={c.id} to={`/categoria/${c.id}`}><Icon name={c.icon} size={18}/>{c.label}</Link>)}</nav>
    {campaigns.length > 0 && <section className="section"><SectionHeading title="Campanhas das lojas" text="Coleções e ações oficiais da Shopee, Mercado Livre e KaBuM!." to="/campanhas" link="Ver todas"/><Carousel label="Campanhas das lojas">{campaigns.map(p => <CampaignSlide key={p.id} promotion={p}/>)}</Carousel></section>}
    {state.error && <Failure error={state.error} retry={state.retry}/>}
    {!!data?.trending?.items.length && <section className="section"><SectionHeading title="Em alta agora!" text="Promoções do que mais está sendo procurado agora." to="/em-alta"/><div className="deal-grid">{data.trending.items.map(d => <DealCard key={d.id} deal={d}/>)}</div></section>}
    <section className="section"><SectionHeading title="Ofertas em destaque" text="Selecionadas por desconto, relevância e atualização recente." to="/ofertas"/>{state.loading ? <Loading count={8}/> : data?.featured.items.length ? <div className="deal-grid">{data.featured.items.map(d => <DealCard key={d.id} deal={d}/>)}</div> : !state.error && <Empty/>}</section>
    {!!data?.bestsellers?.items.length && <section className="section"><SectionHeading title="Mais vendidos" text="Os que mais saem pelos nossos links e nas lojas." to="/ofertas?sort=best_selling"/><div className="deal-grid">{data.bestsellers.items.slice(0, 8).map(d => <DealCard key={d.id} deal={d}/>)}</div></section>}
    {rankings.length > 0 && <section className="section"><SectionHeading title="Rankings de mais vendidos" text="Os campeões de venda de cada categoria que estão em promoção." to="/rankings" link="Ver rankings"/><div className="ranking-grid">{rankings.map(r => <RankingCard key={r.id} ranking={r}/>)}</div></section>}
    {!!data?.discounts.items.length && <section className="section"><SectionHeading title="Maiores descontos" text="Compare a referência do preço antes de escolher." to="/maiores-descontos"/><div className="deal-grid">{data.discounts.items.slice(0, 4).map(d => <DealCard key={d.id} deal={d}/>)}</div></section>}
    {coupons.length > 0 && <section className="section"><SectionHeading title="Cupons" text="Copie o código e confira as regras de cada cupom." to="/cupons" link="Ver cupons"/><div className="promo-grid">{coupons.map(p => <PromotionCard key={p.id} promotion={p}/>)}</div></section>}
    <section className="section"><SectionHeading title="Lojas" to="/lojas"/><div className="store-grid">{STORE_OPTIONS.map(s => <Link className="store-card" key={s.id} to={`/loja/${s.id}`}><span className={`store-mark ${s.id}`}>{s.mark}</span><span><strong>{s.label}</strong><span>{s.caption}</span></span><Icon name="arrow"/></Link>)}</div></section>
  </div>;
}
