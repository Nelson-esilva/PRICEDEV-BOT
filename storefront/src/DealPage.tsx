import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { CATEGORIES, discountOf, money, priceCondition, relativeTime, storeLabel, type List, type PublicDeal } from './api';
import { Breadcrumb, CouponCode, Empty, Failure, Icon, Loading, SectionHeading, StoreTag, share, useRemote, useSaved, useTitle } from './ui';
import DealCard, { DemandLine } from './DealCard';
import ProductImage from './ProductImage';

// Fotos oficiais do catálogo: principal grande + miniaturas (só quando há mais de uma).
function Gallery({ deal }: { deal: PublicDeal }) {
  const photos = deal.gallery?.length ? deal.gallery : deal.image_url ? [deal.image_url] : []; const [index, setIndex] = useState(0);
  if (photos.length < 2) return <div className="detail-media"><ProductImage src={deal.image_url} name={deal.product} eager/></div>;
  const current = Math.min(index, photos.length - 1);
  return <div className="gallery"><div className="gallery-main"><img src={photos[current]} alt={`${deal.product}, foto ${current + 1} de ${photos.length}`}/></div>
    <div className="gallery-thumbs" role="group" aria-label="Fotos do produto">{photos.map((src, i) => <button key={src} aria-current={i === current} aria-label={`Ver foto ${i + 1}`} onClick={() => setIndex(i)} onMouseEnter={() => setIndex(i)}><img src={src} alt="" loading="lazy"/></button>)}</div></div>;
}

export default function DealPage() {
  const { slug = '' } = useParams(); const state = useRemote<PublicDeal>(`/deals/${encodeURIComponent(slug)}`);
  const d = state.data; useTitle(d?.product || 'Detalhes da oferta'); const { saved, toggle } = useSaved();
  const [message, setMessage] = useState('');
  const related = useRemote<List<PublicDeal>>(d ? `/deals?category=${encodeURIComponent(d.category || '')}&limit=5&sort=featured` : null);
  if (state.error) return <div className="container page-space">{state.error.startsWith('Esta oferta') ? <Empty title="Esta oferta não está disponível" text="O preço pode ter mudado ou a oferta pode ter encerrado."/> : <Failure error={state.error} retry={state.retry}/>}</div>;
  if (!d || state.loading) return <div className="container page-space"><Loading count={2}/></div>;
  const discount = discountOf(d); const condition = priceCondition(d); const isSaved = saved.some(item => item.id === d.id);
  const categoryLabel = CATEGORIES.find(c => c.id === d.category)?.label; const others = related.data?.items.filter(item => item.id !== d.id).slice(0, 4) || [];
  return <div className="container page-space"><Breadcrumb items={[['Ofertas', '/ofertas'], ...(d.category ? [[categoryLabel || 'Categoria', `/categoria/${d.category}`] as [string, string]] : [])]}/>
    <section className="deal-detail"><Gallery deal={d}/>
      <div className="detail-info"><div className="detail-meta"><StoreTag store={d.store}/><span>Atualizado {relativeTime(d.updated_at)}</span></div><h1>{d.product}</h1><DemandLine deal={d}/>
        {d.rank_position && d.rank_category_id && <span className="rank-note"><Icon name="trophy" size={16}/>{d.rank_position}º mais vendido em {d.rank_category} · <Link to={`/ranking/${d.rank_category_id}`}>Ver ranking</Link></span>}
        <div className="buy-panel"><div className="detail-price">{(d.list_price || discount != null) && <div>{d.list_price && <s>{money(d.list_price)}</s>}{discount != null && <span className="badge discount">{d.price_max ? 'até ' : ''}−{discount}%</span>}</div>}<strong>{d.price_max ? <small>a partir de </small> : null}{money(d.current_price)}{condition && <small> {condition.when}</small>}</strong><span>{condition?.otherwise ? `${condition.otherwise}. ` : ''}{d.price_condition === 'coupon' && !d.coupon_code ? 'Ative o cupom na página do produto antes de comprar. ' : ''}{d.price_max ? `O menor valor é de uma das opções do anúncio; outras chegam a ${money(d.price_max)}. ` : ''}{d.payment_hint || (d.store === 'shopee' ? 'O valor final na Shopee pode mudar com Pix, cupons e frete; confira antes de pagar.' : 'Confira as condições de pagamento na loja')}</span></div>
          {discount != null && <span className="evidence"><Icon name="check" size={14}/>{d.discount_basis === 'historical' ? 'Queda de preço validada no nosso histórico' : d.price_max ? 'Maior desconto entre as opções, informado pela loja' : 'Percentual de desconto informado pela loja'}</span>}
          {d.coupon_code && <div className="detail-coupon"><span>Cupom desta oferta</span><CouponCode code={d.coupon_code}/><small>Confira as regras de aplicação no checkout.</small></div>}
          <a className="button primary large" href={d.go_path} target="_blank" rel="noopener sponsored">Ver na {storeLabel(d.store)}<Icon name="external" size={18}/></a>
          <div className="detail-actions"><button className={`button secondary ${isSaved ? 'is-saved' : ''}`} aria-pressed={isSaved} onClick={() => toggle(d)}><Icon name="heart" size={18}/>{isSaved ? 'Salvo' : 'Salvar'}</button><button className="button secondary" onClick={async () => setMessage(await share(d.product, `/oferta/${d.slug}`))}><Icon name="share" size={18}/>Compartilhar</button></div>
          <span role="status" className="share-status">{message}</span>
          <p className="fine-print">Você será direcionado à loja. Podemos receber comissão, sem custo extra para você.</p></div></div></section>
    <section className="detail-description"><div className="panel"><h2>Sobre o produto</h2><p>{d.description || 'Consulte a loja de origem para especificações, variações, garantia e disponibilidade.'}</p></div>
      <aside className="panel"><h2>Antes de comprar</h2><ul className="check-list">{['Confira preço e estoque na loja.', 'Frete e prazo dependem do seu endereço.', 'Cupons podem ter limites e condições.', 'Pagamento e entrega são feitos pela loja.'].map(t => <li key={t}><Icon name="check" size={18}/>{t}</li>)}</ul></aside></section>
    {others.length > 0 && <section className="section"><SectionHeading title={categoryLabel ? `Mais em ${categoryLabel}` : 'Outras ofertas'} to={d.category ? `/categoria/${d.category}` : '/ofertas'}/><div className="deal-grid">{others.map(item => <DealCard key={item.id} deal={item}/>)}</div></section>}
    <div className="sticky-buy"><strong>{money(d.current_price)}</strong><a className="button primary" href={d.go_path} rel="noopener sponsored" target="_blank">Ver na loja<Icon name="external" size={16}/></a></div>
  </div>;
}
