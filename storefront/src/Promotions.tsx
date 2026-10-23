import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { dateLabel, hasDeadline, storeLabel, STORE_OPTIONS, queryString, type List, type Promotion } from './api';
import { Breadcrumb, CouponCode, Empty, Failure, Icon, Loading, PageHeading, Pagination, StoreTag, useRemote, useTitle } from './ui';

const PAGE_SIZE = 24;
export function PromotionCard({ promotion }: { promotion: Promotion }) {
  const coupon = promotion.kind === 'coupon';
  return <article className="promo-card">
    {!coupon && promotion.image_url && <img className="promo-image" src={promotion.image_url} alt="" loading="lazy"/>}
    <div className="promo-body"><div className="promo-meta"><StoreTag store={promotion.store}/><span className={coupon ? 'kind coupon' : 'kind'}>{coupon ? 'Cupom' : 'Campanha'}</span></div>
      <h3><Link to={`/campanha/${promotion.slug}`}>{promotion.title}</Link></h3>
      <span className="promo-date"><Icon name="clock" size={16}/>{hasDeadline(promotion.expires_at) ? `Até ${dateLabel(promotion.expires_at)}` : 'Validade nas regras da loja'}</span>
      {promotion.code && <CouponCode code={promotion.code}/>}
      <Link className="text-link" to={`/campanha/${promotion.slug}`}>{coupon ? 'Ver regras do cupom' : 'Explorar campanha'}<Icon name="arrow" size={16}/></Link></div>
  </article>;
}
export function CampaignSlide({ promotion }: { promotion: Promotion }) {
  const mark = STORE_OPTIONS.find(s => s.id === promotion.store)?.mark || promotion.store.slice(0, 2).toUpperCase();
  return <Link className="campaign-slide" to={`/campanha/${promotion.slug}`}>
    <span className="slide-art">{promotion.image_url ? <img src={promotion.image_url} alt="" loading="lazy"/> : <span className={`store-mark ${promotion.store}`}>{mark}</span>}</span>
    <span className="slide-body"><StoreTag store={promotion.store}/><strong>{promotion.title}</strong><span className="promo-date"><Icon name="clock" size={14}/>{hasDeadline(promotion.expires_at) ? `Até ${dateLabel(promotion.expires_at)}` : 'Sem prazo definido'}</span></span>
  </Link>;
}
export function Carousel({ label, children }: { label: string; children: ReactNode }) {
  const track = useRef<HTMLDivElement>(null); const [edge, setEdge] = useState({ start: true, end: true });
  function measure() { const t = track.current; if (t) setEdge({ start: t.scrollLeft <= 4, end: t.scrollLeft + t.clientWidth >= t.scrollWidth - 4 }); }
  useEffect(() => { measure(); window.addEventListener('resize', measure); return () => window.removeEventListener('resize', measure); }, [children]);
  function move(dir: number) { const t = track.current; t?.scrollBy({ left: dir * t.clientWidth * 0.9, behavior: 'smooth' }); }
  return <div className="carousel"><div className="carousel-track" ref={track} onScroll={measure} role="region" aria-label={label} tabIndex={0}>{children}</div>
    {!edge.start && <button className="carousel-button prev" aria-label="Anteriores" onClick={() => move(-1)}><Icon name="back"/></button>}
    {!edge.end && <button className="carousel-button next" aria-label="Próximas" onClick={() => move(1)}><Icon name="chevron"/></button>}</div>;
}
function CampaignsByStore() {
  const state = useRemote<List<Promotion>>(`/promotions?${queryString({ kind: 'campaign', limit: 100 })}`);
  if (state.error) return <Failure error={state.error} retry={state.retry}/>;
  if (state.loading) return <Loading count={3}/>;
  const groups = STORE_OPTIONS.map(s => ({ store: s, items: state.data?.items.filter(p => p.store === s.id) || [] })).filter(g => g.items.length);
  if (!groups.length) return <Empty title="Nenhuma campanha ativa agora" text="Mostramos somente condições publicadas pelas lojas. Volte em breve ou veja as ofertas disponíveis."/>;
  return <>{groups.map(({ store, items }) => <section className="section" key={store.id}><div className="section-heading"><div className="store-heading"><span className={`store-mark ${store.id}`}>{store.mark}</span><div><h2>{store.label}</h2><p>{items.length} {items.length === 1 ? 'campanha ativa' : 'campanhas ativas'}</p></div></div><Link className="text-link" to={`/loja/${store.id}`}>Ver loja<Icon name="arrow" size={16}/></Link></div>
    <Carousel label={`Campanhas ${store.label}`}>{items.map(p => <CampaignSlide key={p.id} promotion={p}/>)}</Carousel></section>)}</>;
}
export default function Promotions({ kind }: { kind: 'campaign' | 'coupon' }) {
  const [params, setParams] = useSearchParams(); const store = params.get('store') || ''; const page = Math.max(1, Number(params.get('page')) || 1);
  const title = kind === 'coupon' ? 'Cupons' : 'Campanhas'; useTitle(kind === 'coupon' ? 'Cupons disponíveis' : 'Campanhas atuais');
  const state = useRemote<List<Promotion>>(kind === 'coupon' ? `/promotions?${queryString({ kind, store, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE })}` : null);
  function update(key: string, value: string) { const next = new URLSearchParams(params); value ? next.set(key, value) : next.delete(key); if (key !== 'page') next.delete('page'); setParams(next); }
  return <div className="container page-space"><Breadcrumb items={[[title]]}/><PageHeading title={title} text={kind === 'coupon' ? 'Escolha a loja, copie o código e confira as condições antes de comprar.' : 'Ações oficiais das lojas, com prazo e regras visíveis.'}/>
    {kind === 'campaign' ? <CampaignsByStore/> : <><div className="segmented" role="group" aria-label="Filtrar por loja"><button aria-pressed={!store} onClick={() => update('store', '')}>Todas</button>{STORE_OPTIONS.map(s => <button key={s.id} aria-pressed={store === s.id} onClick={() => update('store', s.id)}>{s.label}</button>)}</div>
    {state.error ? <Failure error={state.error} retry={state.retry}/> : state.loading ? <Loading count={3}/> : !state.data?.items.length ? <Empty title={kind === 'coupon' ? 'Nenhum cupom ativo para esta seleção' : 'Nenhuma campanha ativa agora'} text="Mostramos somente condições publicadas pelas lojas. Volte em breve ou veja as ofertas disponíveis."/>
      : <><div className="promo-grid">{state.data.items.map(p => <PromotionCard key={p.id} promotion={p}/>)}</div><Pagination page={page} total={state.data.total} pageSize={PAGE_SIZE} onPage={n => update('page', String(n))}/></>}</>}
  </div>;
}
export function CampaignDetail() {
  const { slug } = useParams(); const state = useRemote<Promotion>(`/promotions/${encodeURIComponent(slug || '')}`); useTitle(state.data?.title || 'Campanha');
  if (state.error) return <div className="container page-space">{state.error.startsWith('Esta oferta') ? <Empty title="Esta campanha não está disponível" text="Ela pode ter terminado. Veja outras campanhas e cupons ativos."/> : <Failure error={state.error} retry={state.retry}/>}</div>;
  if (!state.data || state.loading) return <div className="container page-space"><Loading count={2}/></div>;
  const p = state.data; const coupon = p.kind === 'coupon';
  return <div className="container page-space"><Breadcrumb items={[[coupon ? 'Cupons' : 'Campanhas', coupon ? '/cupons' : '/campanhas']]}/>
    <section className="campaign-detail">{p.image_url ? <img className="campaign-image" src={p.image_url} alt=""/> : <div className="campaign-placeholder" aria-hidden="true"><Icon name={coupon ? 'ticket' : 'tag'} size={64}/></div>}
      <div className="campaign-info"><div className="promo-meta"><StoreTag store={p.store}/><span className={coupon ? 'kind coupon' : 'kind'}>{coupon ? 'Cupom' : 'Campanha'}</span></div><h1>{p.title}</h1>
        <p>{p.description || 'Confira os produtos participantes e as condições na loja.'}</p>
        <span className="promo-date"><Icon name="clock" size={16}/>{hasDeadline(p.expires_at) ? `Válido até ${dateLabel(p.expires_at)}` : 'Consulte a validade na loja'}</span>
        {p.code && <CouponCode code={p.code}/>}
        <a className="button primary large" href={p.go_path} target="_blank" rel="noopener sponsored">{coupon ? 'Usar cupom na loja' : 'Ver campanha na loja'}<Icon name="external" size={18}/></a>
        <p className="fine-print">Link de afiliado. A compra é finalizada na {storeLabel(p.store)}.</p></div></section>
    <section className="panel terms"><h2>Antes de aproveitar</h2><p>{p.terms || 'Consulte a página da campanha na loja para verificar elegibilidade, disponibilidade e condições de uso.'}</p><p>O desconto vale somente para os produtos participantes. Valores mínimos, limites e formas de pagamento podem se aplicar. Não calculamos desconto sobre produtos sem confirmação de participação.</p></section>
    <Link className="text-link" to={`/loja/${p.store}`}>Mais na {storeLabel(p.store)}<Icon name="arrow" size={16}/></Link></div>;
}
