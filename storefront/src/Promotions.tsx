import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { dateLabel, hasDeadline, storeLabel, STORE_OPTIONS, queryString, type List, type Promotion } from './api';
import { revealImage } from './ProductImage';
import { Breadcrumb, CouponCode, Empty, Failure, Icon, Loading, PageHeading, Pagination, StoreTag, useRemote, useTitle } from './ui';

const PAGE_SIZE = 24;
export function PromotionCard({ promotion }: { promotion: Promotion }) {
  const coupon = promotion.kind === 'coupon';
  return <article className="promo-card">
    {!coupon && promotion.image_url && <img className="promo-image fade-img" src={promotion.image_url} alt="" loading="lazy" onLoad={revealImage}/>}
    <div className="promo-body"><div className="promo-meta"><StoreTag store={promotion.store}/><span className={coupon ? 'kind coupon' : 'kind'}>{coupon ? 'Cupom' : 'Campanha'}</span></div>
      <h3><Link to={`/campanha/${promotion.slug}`}>{promotion.title}</Link></h3>
      <span className="promo-date"><Icon name="clock" size={16}/>{hasDeadline(promotion.expires_at) ? `Até ${dateLabel(promotion.expires_at)}` : 'Validade nas regras da loja'}</span>
      {promotion.code && <CouponCode code={promotion.code}/>}
      <Link className="text-link" to={`/campanha/${promotion.slug}`}>{coupon ? 'Ver regras do cupom' : 'Explorar campanha'}<Icon name="arrow" size={16}/></Link></div>
  </article>;
}
const AUTOPLAY_MS = 6000;
// Passa sozinho a cada 6 s. Pausa com mouse/foco, aba oculta ou pelo botão; sem autoplay com "reduzir movimento".
// O tempo é o da própria animação da barrinha: ao pausar ela congela e retoma de onde parou.
export function BannerRotator({ items }: { items: Promotion[] }) {
  const count = items.length;
  const [index, setIndex] = useState(0); const [paused, setPaused] = useState(false);
  const [holding, setHolding] = useState(false); const [hidden, setHidden] = useState(false);
  const [reduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const touchX = useRef<number | null>(null);
  useEffect(() => {
    const onVisibility = () => setHidden(document.hidden);
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);
  if (!count) return null;
  const current = index % count; const autoplay = count > 1 && !reduced;
  const running = autoplay && !paused && !holding && !hidden;
  const go = (step: number) => setIndex(i => (i + step + count) % count);
  return <section className={`banner-rotator ${running ? 'running' : ''}`} aria-roledescription="carrossel" aria-label="Campanhas em destaque"
    onMouseEnter={() => setHolding(true)} onMouseLeave={() => setHolding(false)}
    onFocus={e => { if ((e.target as HTMLElement).matches(':focus-visible')) setHolding(true); }} onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setHolding(false); }}
    onTouchStart={e => { touchX.current = e.touches[0].clientX; setHolding(true); }}
    onTouchEnd={e => { const dx = e.changedTouches[0].clientX - (touchX.current ?? e.changedTouches[0].clientX); if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1); touchX.current = null; setHolding(false); }}>
    <div className="banner-track" style={{ transform: `translateX(-${current * 100}%)` }} aria-live={running ? 'off' : 'polite'}>
      {items.map((item, n) => <Link key={item.id} className="banner-slide" to={`/campanha/${item.slug}`} aria-hidden={n !== current} tabIndex={n === current ? 0 : -1}
        aria-roledescription="slide" aria-label={`${n + 1} de ${count}: ${item.title}`}>
        <img className="fade-img" src={item.image_url || ''} alt={item.title} loading={n === 0 ? 'eager' : 'lazy'} draggable={false} onLoad={revealImage}/></Link>)}
    </div>
    {count > 1 && <><button className="banner-nav prev" aria-label="Banner anterior" onClick={() => go(-1)}><Icon name="back"/></button>
      <button className="banner-nav next" aria-label="Próximo banner" onClick={() => go(1)}><Icon name="chevron"/></button>
      <div className="banner-controls">
        <div className="banner-dots">{items.map((item, n) => <button key={item.id} aria-label={`Ir para o banner ${n + 1} de ${count}`} aria-current={n === current} onClick={() => setIndex(n)}>
          {n === current && autoplay && <span key={index} className="dot-fill" style={{ animationDuration: `${AUTOPLAY_MS}ms` }} onAnimationEnd={() => go(1)}/>}</button>)}</div>
        {autoplay && <button className="banner-pause" aria-label={paused ? 'Continuar passagem automática' : 'Pausar passagem automática'} aria-pressed={paused} onClick={() => setPaused(v => !v)}><Icon name={paused ? 'play' : 'pause'} size={14}/></button>}
      </div></>}
  </section>;
}
// Banners oficiais do ML são largos (1920×500); nas demais lojas a imagem é quadrada.
export const isBanner = (p: Promotion) => p.store === 'mercadolivre' && !!p.image_url;
export function CampaignSlide({ promotion }: { promotion: Promotion }) {
  const mark = STORE_OPTIONS.find(s => s.id === promotion.store)?.mark || promotion.store.slice(0, 2).toUpperCase();
  return <Link className={`campaign-slide ${isBanner(promotion) ? 'wide' : ''}`} to={`/campanha/${promotion.slug}`}>
    <span className="slide-art">{promotion.image_url ? <img className="fade-img" src={promotion.image_url} alt="" loading="lazy" onLoad={revealImage}/> : <span className={`store-mark ${promotion.store}`}>{mark}</span>}</span>
    <span className="slide-body"><StoreTag store={promotion.store}/><strong>{promotion.title}</strong><span className="promo-date"><Icon name="clock" size={14}/>{hasDeadline(promotion.expires_at) ? `Até ${dateLabel(promotion.expires_at)}` : 'Sem prazo definido'}</span></span>
  </Link>;
}
export function Carousel({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  const track = useRef<HTMLDivElement>(null); const [edge, setEdge] = useState({ start: true, end: true });
  function measure() { const t = track.current; if (t) setEdge({ start: t.scrollLeft <= 4, end: t.scrollLeft + t.clientWidth >= t.scrollWidth - 4 }); }
  useEffect(() => { measure(); window.addEventListener('resize', measure); return () => window.removeEventListener('resize', measure); }, [children]);
  function move(dir: number) { const t = track.current; t?.scrollBy({ left: dir * t.clientWidth * 0.9, behavior: 'smooth' }); }
  return <div className={`carousel ${wide ? 'wide' : ''}`}><div className="carousel-track" ref={track} onScroll={measure} role="region" aria-label={label} tabIndex={0}>{children}</div>
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
    <Carousel label={`Campanhas ${store.label}`} wide={items.every(isBanner)}>{items.map(p => <CampaignSlide key={p.id} promotion={p}/>)}</Carousel></section>)}</>;
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
    {isBanner(p) && <img className="campaign-banner" src={p.image_url || ''} alt={p.title}/>}
    <section className="campaign-detail">{isBanner(p) ? null : p.image_url ? <img className="campaign-image" src={p.image_url} alt=""/> : <div className="campaign-placeholder" aria-hidden="true"><Icon name={coupon ? 'ticket' : 'tag'} size={64}/></div>}
      <div className="campaign-info"><div className="promo-meta"><StoreTag store={p.store}/><span className={coupon ? 'kind coupon' : 'kind'}>{coupon ? 'Cupom' : 'Campanha'}</span></div><h1>{p.title}</h1>
        <p>{p.description || 'Confira os produtos participantes e as condições na loja.'}</p>
        <span className="promo-date"><Icon name="clock" size={16}/>{hasDeadline(p.expires_at) ? `Válido até ${dateLabel(p.expires_at)}` : 'Consulte a validade na loja'}</span>
        {p.code && <CouponCode code={p.code}/>}
        <a className="button primary large" href={p.go_path} target="_blank" rel="noopener sponsored">{coupon ? 'Usar cupom na loja' : 'Ver campanha na loja'}<Icon name="external" size={18}/></a>
        <p className="fine-print">Link de afiliado. A compra é finalizada na {storeLabel(p.store)}.</p></div></section>
    <section className="panel terms"><h2>Antes de aproveitar</h2><p>{p.terms || 'Consulte a página da campanha na loja para verificar elegibilidade, disponibilidade e condições de uso.'}</p><p>O desconto vale somente para os produtos participantes. Valores mínimos, limites e formas de pagamento podem se aplicar. Não calculamos desconto sobre produtos sem confirmação de participação.</p></section>
    <Link className="text-link" to={`/loja/${p.store}`}>Mais na {storeLabel(p.store)}<Icon name="arrow" size={16}/></Link></div>;
}
