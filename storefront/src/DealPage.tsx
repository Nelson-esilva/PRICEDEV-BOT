import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  buyLabel,
  discountOf,
  fetchDeal,
  money,
  relativeTime,
  storeLabel,
  type PublicDeal,
} from "./api";

export default function DealPage() {
  const { slug = "" } = useParams();
  const [deal, setDeal] = useState<PublicDeal | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchDeal(slug)
      .then((item) => {
        if (cancelled) return;
        setDeal(item);
        setMissing(item == null);
      })
      .catch(() => {
        if (!cancelled) setError("Não foi possível abrir esta oferta.");
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (missing) {
    return (
      <main className="empty">
        <h1>Oferta encerrada</h1>
        <p>Esse preço não está mais na vitrine. O valor na loja pode ter mudado.</p>
        <Link to="/">Ver ofertas ativas</Link>
      </main>
    );
  }
  if (error) {
    return (
      <main className="empty">
        <h1>Algo falhou</h1>
        <p>{error}</p>
        <Link to="/">Voltar às ofertas</Link>
      </main>
    );
  }
  if (!deal) {
    return (
      <main>
        <p className="muted">Carregando oferta…</p>
      </main>
    );
  }

  const discount = discountOf(deal);
  return (
    <main className="deal-page">
      <Link className="back" to="/">
        ← Ofertas
      </Link>
      <div className="deal-hero">
        <div className="media tall">
          {deal.image_url ? <img src={deal.image_url} alt={deal.product} /> : <div className="placeholder" />}
          {discount != null ? <span className="disc">-{discount}%</span> : null}
        </div>
        <div className="deal-info">
          <p className={`store-name ${deal.store}`}>{storeLabel(deal.store)}</p>
          <h1>{deal.product}</h1>
          <p className="fresh">Atualizado {relativeTime(deal.updated_at)}</p>
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
          {deal.description ? <p className="desc">{deal.description}</p> : null}
          <a className="compare" href={deal.go_path} rel="noopener sponsored" target="_blank">
            {buyLabel(deal.store)}
          </a>
          <p className="legal-note">
            Link de afiliado: podemos receber comissão se você comprar. O preço final é o da{" "}
            {storeLabel(deal.store)} e pode mudar no checkout.
          </p>
        </div>
      </div>
    </main>
  );
}
