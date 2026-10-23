import { useRef, type FormEvent } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { CATEGORIES, STORE_OPTIONS, queryString, storeLabel, type List, type PublicDeal, type Promotion } from './api';
import { Breadcrumb, Empty, Failure, Icon, Loading, PageHeading, Pagination, SectionHeading, useRemote, useSaved, useTitle } from './ui';
import DealCard from './DealCard';
import { PromotionCard } from './Promotions';

const PAGE_SIZE = 24;
const FILTER_KEYS = ['store', 'category', 'min_price', 'max_price', 'min_discount', 'has_coupon'];
export default function Catalog() {
  const route = useParams(); const location = useLocation(); const [params, setParams] = useSearchParams();
  const discountPage = location.pathname === '/maiores-descontos'; const q = params.get('q') || '';
  const category = route.category || params.get('category') || ''; const store = route.store || params.get('store') || '';
  const sort = params.get('sort') || (discountPage ? 'discount' : 'featured');
  const page = Math.max(1, Number(params.get('page')) || 1); const dialog = useRef<HTMLDialogElement>(null);
  const categoryLabel = CATEGORIES.find(c => c.id === category)?.label;
  const title = q ? `Resultados para “${q}”` : route.store ? storeLabel(store) : categoryLabel ? categoryLabel : discountPage ? 'Maiores descontos' : location.pathname === '/busca' ? 'Busca' : 'Todas as ofertas';
  useTitle(q ? `Busca: ${q}` : title);
  const state = useRemote<List<PublicDeal>>(`/deals?${queryString({ q, category, store, sort, min_price: params.get('min_price'), max_price: params.get('max_price'), min_discount: params.get('min_discount'), has_coupon: params.get('has_coupon'), limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE })}`);
  const few = !!state.data && state.data.total < 5 && page === 1;
  const suggestions = useRemote<List<PublicDeal>>(few ? `/deals?${queryString({ category: route.category, store: route.store, sort: 'featured', limit: 12 })}` : null);
  const shown = new Set(state.data?.items.map(d => d.id)); const extra = suggestions.data?.items.filter(d => !shown.has(d.id)).slice(0, 8) || [];
  const promotions = useRemote<List<Promotion>>(route.store ? `/promotions?${queryString({ store: route.store, limit: 6 })}` : null);
  function update(key: string, value: string) { const next = new URLSearchParams(params); value ? next.set(key, value) : next.delete(key); if (key !== 'page') next.delete('page'); setParams(next); }
  function apply(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = new FormData(e.currentTarget); const next = new URLSearchParams(params);
    for (const key of FILTER_KEYS) {
      if ((key === 'store' && route.store) || (key === 'category' && route.category)) continue;
      const value = String(form.get(key) || ''); value ? next.set(key, value) : next.delete(key);
    }
    next.delete('page'); setParams(next); dialog.current?.close();
  }
  function clear() { const next = new URLSearchParams(); if (q) next.set('q', q); setParams(next); dialog.current?.close(); }
  const active = [...params.entries()].filter(([k, v]) => FILTER_KEYS.includes(k) && v);
  const minDiscount = params.get('min_discount') || '';
  function filters(mobile = false) {
    return <form onSubmit={apply} key={`${params.toString()}-${mobile}`} className="filter-form">
      <div className="filter-heading"><h2>Filtros</h2>{active.length > 0 && <button type="button" className="text-button" onClick={clear}>Limpar</button>}</div>
      {!route.store && <label className="field">Loja<select name="store" defaultValue={store}><option value="">Todas as lojas</option>{STORE_OPTIONS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label>}
      {!route.category && <label className="field">Categoria<select name="category" defaultValue={category}><option value="">Todas as categorias</option>{CATEGORIES.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>}
      <fieldset><legend>Preço</legend><div className="price-inputs"><label>De R$<input type="number" min="0" step="0.01" name="min_price" placeholder="0" defaultValue={params.get('min_price') || ''}/></label><label>Até R$<input type="number" min="0" step="0.01" name="max_price" placeholder="Máx." defaultValue={params.get('max_price') || ''}/></label></div></fieldset>
      <fieldset><legend>Desconto mínimo</legend><div className="pill-options">{['', '10', '20', '30', '50'].map(n => <label key={n}><input type="radio" name="min_discount" value={n} defaultChecked={minDiscount === n}/><span>{n ? `${n}%` : 'Qualquer'}</span></label>)}</div></fieldset>
      <label className="checkbox"><input type="checkbox" name="has_coupon" value="true" defaultChecked={params.get('has_coupon') === 'true'}/>Somente com cupom</label>
      <button className="button primary" type="submit">Aplicar filtros</button>
      <p className="filter-note">O percentual pode vir da loja ou do nosso histórico de preços. Cada oferta indica a origem.</p></form>;
  }
  function chipLabel(k: string, v: string) { return k === 'store' ? storeLabel(v) : k === 'category' ? CATEGORIES.find(c => c.id === v)?.label || v : k === 'min_price' ? `A partir de R$ ${v}` : k === 'max_price' ? `Até R$ ${v}` : k === 'min_discount' ? `Desconto ≥ ${v}%` : 'Com cupom'; }
  const kabum = route.store === 'kabum';
  return <div className="container page-space"><Breadcrumb items={[[q ? 'Busca' : title]]}/>
    <PageHeading title={title} text={kabum ? 'Campanhas e cupons oficiais. Confira as condições de cada oportunidade.' : 'A compra é sempre finalizada na loja de origem.'}/>
    {route.store && promotions.error && <Failure error={promotions.error} retry={promotions.retry}/>}
    {route.store && !!promotions.data?.items.length && <section className="section"><SectionHeading title="Campanhas e cupons da loja"/><div className="promo-grid">{promotions.data.items.map(p => <PromotionCard key={p.id} promotion={p}/>)}</div></section>}
    <div className="catalog-layout"><aside className="filter-panel">{filters()}</aside>
      <section className="catalog-results" aria-label="Resultados">
        <div className="results-toolbar"><span><strong>{state.data?.total ?? '…'}</strong> {state.data?.total === 1 ? 'oferta' : 'ofertas'}</span><button className="button secondary mobile-filter" onClick={() => dialog.current?.showModal()}><Icon name="filter" size={16}/>Filtros{active.length > 0 && <span className="count">{active.length}</span>}</button>
          <label className="sort-label">Ordenar por<select value={sort} onChange={e => update('sort', e.target.value)}><option value="featured">Destaques</option><option value="recent">Mais recentes</option><option value="discount">Maior desconto</option><option value="price_asc">Menor preço</option><option value="price_desc">Maior preço</option></select></label></div>
        {active.length > 0 && <div className="filter-chips">{active.map(([k, v]) => <button key={k} onClick={() => update(k, '')} aria-label={`Remover filtro ${chipLabel(k, v)}`}>{chipLabel(k, v)}<Icon name="close" size={14}/></button>)}</div>}
        {state.error ? <Failure error={state.error} retry={state.retry}/> : state.loading && !state.data ? <Loading count={6}/> : !state.data?.items.length ? <Empty title={kabum ? 'Veja as campanhas e cupons desta loja' : 'Nenhuma oferta com esses filtros'} text={kabum ? 'Produtos de catálogo não são publicados em massa. As campanhas disponíveis aparecem acima.' : 'Tente remover algum filtro ou buscar por outro termo.'}/>
          : <><div className={`deal-grid ${state.loading ? 'refreshing' : ''}`} aria-busy={state.loading}>{state.data.items.map(d => <DealCard key={d.id} deal={d}/>)}</div><Pagination page={page} total={state.data.total} pageSize={PAGE_SIZE} onPage={n => update('page', String(n))}/></>}
        {few && extra.length > 0 && <section className="section suggestions"><SectionHeading title={state.data?.total ? 'Você também pode gostar' : 'Ofertas em destaque'} to="/ofertas"/><div className="deal-grid">{extra.map(d => <DealCard key={d.id} deal={d}/>)}</div></section>}
      </section></div>
    <dialog className="sheet" ref={dialog}><div className="sheet-top"><h2>Filtros</h2><button className="icon-button" aria-label="Fechar filtros" onClick={() => dialog.current?.close()}><Icon name="close"/></button></div>{filters(true)}</dialog></div>;
}

export function Favorites() {
  useTitle('Favoritos'); const { saved } = useSaved();
  const state = useRemote<List<PublicDeal>>(saved.length ? `/deals?${queryString({ ids: saved.map(d => d.id).join(','), limit: 100 })}` : null);
  const live = new Map(state.data?.items.map(d => [d.id, d]));
  return <div className="container page-space"><Breadcrumb items={[['Favoritos']]}/><PageHeading title="Favoritos" text="Salvos neste dispositivo, sem cadastro. Ofertas encerradas ficam sinalizadas."/>
    {!saved.length ? <Empty title="Nenhuma oferta salva" text="Toque no coração de uma oferta para encontrá-la aqui depois."/> : state.error ? <Failure error={state.error} retry={state.retry}/> : state.loading ? <Loading/> : <div className="deal-grid">{saved.map(d => <DealCard key={d.id} deal={live.get(d.id) || d} expired={!live.has(d.id)}/>)}</div>}</div>;
}
export function Directory({ kind }: { kind: 'categories' | 'stores' }) {
  const categories = kind === 'categories'; const title = categories ? 'Categorias' : 'Lojas'; useTitle(title);
  return <div className="container page-space"><Breadcrumb items={[[title]]}/><PageHeading title={title} text={categories ? 'Escolha uma categoria para ver as ofertas.' : 'Ofertas, campanhas e cupons organizados pela loja de origem.'}/>
    {categories ? <div className="category-grid">{CATEGORIES.map(c => <Link key={c.id} to={`/categoria/${c.id}`}><span className="category-icon"><Icon name={c.icon} size={24}/></span><strong>{c.label}</strong><Icon name="chevron" size={16}/></Link>)}</div>
      : <div className="store-grid">{STORE_OPTIONS.map(s => <Link className="store-card" key={s.id} to={`/loja/${s.id}`}><span className={`store-mark ${s.id}`}>{s.mark}</span><span><strong>{s.label}</strong><span>{s.caption}</span></span><Icon name="arrow"/></Link>)}</div>}</div>;
}
