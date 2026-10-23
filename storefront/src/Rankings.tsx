import { Link, useParams } from 'react-router-dom';
import { discountOf, money, priceCondition, type List, type PublicDeal, type Ranking } from './api';
import { Breadcrumb, Empty, Failure, Icon, Loading, PageHeading, useRemote, useTitle } from './ui';
import ProductImage from './ProductImage';

export function RankingCard({ ranking }: { ranking: Ranking }) {
  return <Link className="ranking-card" to={`/ranking/${ranking.id}`}>{ranking.image_url ? <img src={ranking.image_url} alt="" loading="lazy"/> : <Icon name="trophy" size={40}/>}
    <span><strong>{ranking.label}</strong><small>{ranking.count} {ranking.count === 1 ? 'oferta' : 'ofertas'} no ranking</small></span></Link>;
}

export function RankingIndex() {
  useTitle('Rankings de mais vendidos'); const state = useRemote<List<Ranking>>('/rankings?min_items=2');
  return <div className="container page-space"><Breadcrumb items={[['Rankings']]}/>
    <PageHeading title="Rankings de mais vendidos" text="Os produtos que mais vendem em cada categoria, com as promoções que encontramos para eles."/>
    {state.error ? <Failure error={state.error} retry={state.retry}/> : state.loading && !state.data ? <Loading count={6}/>
      : state.data?.items.length ? <div className="ranking-grid">{state.data.items.map(r => <RankingCard key={r.id} ranking={r}/>)}</div>
      : <Empty title="Nenhum ranking com ofertas agora" text="Os rankings aparecem quando há promoções dos produtos mais vendidos."/>}
  </div>;
}

export function RankingPage() {
  const { id = '' } = useParams();
  const state = useRemote<List<PublicDeal>>(`/deals?ranking=${encodeURIComponent(id)}&sort=rank&limit=50`);
  const label = state.data?.items[0]?.rank_category || 'Ranking'; useTitle(`Mais vendidos em ${label}`);
  return <div className="container page-space"><Breadcrumb items={[['Rankings', '/rankings'], [label]]}/>
    <PageHeading title={`Mais vendidos em ${label}`} text="Posição no ranking oficial de mais vendidos da categoria. Mostramos as posições que estão em promoção agora."/>
    {state.error ? <Failure error={state.error} retry={state.retry}/> : state.loading && !state.data ? <Loading count={4}/>
      : state.data?.items.length ? <ol className="rank-list">{state.data.items.map(d => <RankRow key={d.id} deal={d}/>)}</ol>
      : <Empty title="Nenhuma oferta neste ranking agora" text="Volte mais tarde ou veja outros rankings."/>}
  </div>;
}

function RankRow({ deal }: { deal: PublicDeal }) {
  const discount = discountOf(deal); const condition = priceCondition(deal);
  return <li className="rank-row"><span className="rank-pos" aria-label={`Posição ${deal.rank_position}`}>{deal.rank_position}º</span>
    <Link to={`/oferta/${deal.slug}`} tabIndex={-1} aria-hidden="true"><ProductImage src={deal.image_url} name={deal.product}/></Link>
    <div className="rank-info"><h2><Link to={`/oferta/${deal.slug}`}>{deal.product}</Link></h2>
      <div className="rank-price">{deal.list_price && <s>{money(deal.list_price)}</s>}<strong>{money(deal.current_price)}</strong>{condition && <small>{condition.when}</small>}{discount != null && <span className="badge discount">−{discount}%</span>}</div>
      {deal.free_shipping && <span className="ship-free"><Icon name="truck" size={13}/>Frete grátis</span>}</div>
    <a className="button primary" href={deal.go_path} target="_blank" rel="noopener sponsored">Ver oferta<Icon name="arrow" size={16}/></a></li>;
}
