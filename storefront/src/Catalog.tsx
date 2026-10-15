import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { CATEGORIES, STORE_OPTIONS, fetchDeals, storeLabel, type PublicDeal } from "./api";
import DealCard from "./DealCard";
import Pager from "./Pager";

const PAGE_SIZE = 48;

export default function Catalog() {
  const { store, category } = useParams();
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<PublicDeal[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const storeFilter = store ?? "";
  const categoryFilter = category ?? "";

  useEffect(() => {
    setPage(1);
  }, [storeFilter, categoryFilter, q]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDeals({
      q,
      store: storeFilter,
      category: categoryFilter,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
        setError("");
      })
      .catch(() => {
        if (!cancelled) setError("Não foi possível carregar as ofertas agora.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [q, storeFilter, categoryFilter, page]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const heading = useMemo(() => {
    if (q) return `Resultados para “${q}”`;
    if (storeFilter) return `Ofertas ${storeLabel(storeFilter)}`;
    if (categoryFilter) {
      const label = CATEGORIES.find((item) => item.id === categoryFilter)?.label;
      return label || "Ofertas";
    }
    return "Ofertas de hoje";
  }, [q, storeFilter, categoryFilter]);

  return (
    <main>
      <section className="hero">
        <div>
          <h1>{heading}</h1>
          <p>Shopee e Mercado Livre, com o nosso link de afiliado. O preço vale na loja.</p>
        </div>
      </section>
      <div className="stores-row">
        <span className="row-label">Loja</span>
        {STORE_OPTIONS.map((item) => (
          <Link
            key={item.id || "all"}
            className={`store-chip ${item.id} ${storeFilter === item.id ? "on" : ""}`}
            to={item.id ? `/loja/${item.id}` : "/"}
          >
            {item.label}
          </Link>
        ))}
      </div>
      <div className="stores-row cats">
        <span className="row-label">Categoria</span>
        {CATEGORIES.map((item) => (
          <Link
            key={item.id || "all-cat"}
            className={`store-chip ${categoryFilter === item.id ? "on" : ""}`}
            to={item.id ? `/categoria/${item.id}` : "/"}
          >
            {item.label}
          </Link>
        ))}
      </div>
      {error ? <p className="banner">{error}</p> : null}
      {loading && items.length === 0 ? <p className="muted">Carregando ofertas…</p> : null}
      {!loading && items.length === 0 ? (
        <section className="empty">
          <h2>Nenhuma oferta por aqui</h2>
          <p>Tente outra loja, categoria ou termo. As vitrines oficiais atualizam ao longo do dia.</p>
          <Link to="/">Ver todas</Link>
        </section>
      ) : (
        <div className="grid">
          {items.map((deal) => (
            <DealCard key={deal.id} deal={deal} />
          ))}
        </div>
      )}
      <Pager page={page} pageCount={pageCount} total={total} pageSize={PAGE_SIZE} onPage={setPage} />
    </main>
  );
}
