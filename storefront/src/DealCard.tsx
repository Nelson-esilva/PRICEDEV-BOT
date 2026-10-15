import { Link } from "react-router-dom";
import { buyLabel, discountOf, money, relativeTime, storeLabel, type PublicDeal } from "./api";

export default function DealCard({ deal }: { deal: PublicDeal }) {
  const discount = discountOf(deal);
  const href = `/oferta/${deal.slug}`;
  return (
    <article className="deal">
      <Link className="media" to={href}>
        {deal.image_url ? <img src={deal.image_url} alt={deal.product} /> : <div className="placeholder" />}
        {discount != null ? <span className="disc">-{discount}%</span> : null}
      </Link>
      <div className="body">
        <div className="store-row">
          <span className={`store-name ${deal.store}`}>{storeLabel(deal.store)}</span>
          <span className="fresh">Atualizado {relativeTime(deal.updated_at)}</span>
        </div>
        <h3>
          <Link to={href}>{deal.product}</Link>
        </h3>
        <div className="price">
          <strong>{money(deal.current_price)}</strong>
          {deal.list_price ? <s>{money(deal.list_price)}</s> : null}
        </div>
        {deal.coupon_code ? (
          <div className="coupon">
            Cupom <b>{deal.coupon_code}</b>
          </div>
        ) : null}
        {deal.payment_hint ? <p className="hint">{deal.payment_hint}</p> : null}
        <div className="foot">
          <span>{deal.merchant || storeLabel(deal.store)}</span>
          <a className="buy" href={deal.go_path} rel="noopener sponsored" target="_blank">
            {buyLabel(deal.store)}
          </a>
        </div>
      </div>
    </article>
  );
}
