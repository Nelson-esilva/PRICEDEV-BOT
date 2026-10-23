import { Link } from 'react-router-dom';
import { discountOf, money, relativeTime, type PublicDeal } from './api';
import { Icon, StoreTag, useSaved } from './ui';
import ProductImage from './ProductImage';

export default function DealCard({ deal, expired = false }: { deal: PublicDeal; expired?: boolean }) {
  const { saved, toggle } = useSaved(); const isSaved = saved.some(d => d.id === deal.id); const discount = discountOf(deal);
  return <article className={`deal-card ${expired ? 'expired' : ''}`}>
    <div className="deal-media"><Link to={`/oferta/${deal.slug}`} tabIndex={-1} aria-hidden="true"><ProductImage src={deal.image_url} name={deal.product}/></Link>
      {expired ? <span className="badge muted">Encerrada</span> : discount != null ? <span className="badge discount">−{discount}%</span> : deal.coupon_code ? <span className="badge coupon"><Icon name="ticket" size={14}/>Com cupom</span> : null}
      <button className={`save-button ${isSaved ? 'saved' : ''}`} onClick={() => toggle(deal)} aria-label={isSaved ? 'Remover dos favoritos' : 'Salvar oferta'} aria-pressed={isSaved}><Icon name="heart" size={20}/></button>
    </div>
    <div className="deal-body"><StoreTag store={deal.store} extra={relativeTime(deal.updated_at)}/>
      <h3><Link to={`/oferta/${deal.slug}`}>{deal.product}</Link></h3>
      <div className="card-price">{deal.list_price ? <s>{money(deal.list_price)}</s> : <span aria-hidden="true"/>}<strong>{money(deal.current_price)}</strong>
        <span>{deal.payment_hint || (deal.coupon_code ? `Use o cupom ${deal.coupon_code}` : discount != null ? (deal.discount_basis === 'historical' ? 'Queda validada no histórico' : 'Desconto anunciado pela loja') : 'Confira as condições na loja')}</span></div>
      {expired ? <span className="button disabled">Oferta encerrada</span> : <a className="button primary" href={deal.go_path} target="_blank" rel="noopener sponsored">Ver oferta<Icon name="arrow" size={16}/></a>}
    </div>
  </article>;
}
