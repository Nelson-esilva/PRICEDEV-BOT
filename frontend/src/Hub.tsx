import { useEffect, useMemo, useState } from "react";
import { fetchOpportunities, type Opportunity } from "./api";

const HUB_CATEGORIES = [
  { id: "", label: "Tudo" },
  { id: "Acessórios para Veículos", label: "Acessórios para Veículos" },
  { id: "Agro", label: "Agro" },
  { id: "Antiguidades e Coleções", label: "Antiguidades e Coleções" },
  { id: "Arte, Papelaria e Armarinho", label: "Arte, Papelaria e Armarinho" },
  { id: "Bebês", label: "Bebês" },
  { id: "Beleza e Cuidado Pessoal", label: "Beleza e Cuidado Pessoal" },
  { id: "Brinquedos e Hobbies", label: "Brinquedos e Hobbies" },
  { id: "Calçados, Roupas e Bolsas", label: "Calçados, Roupas e Bolsas" },
  { id: "Casa, Móveis e Decoração", label: "Casa, Móveis e Decoração" },
  { id: "Celulares e Telefones", label: "Celulares e Telefones" },
  { id: "Construção", label: "Construção" },
  { id: "Câmeras e Acessórios", label: "Câmeras e Acessórios" },
  { id: "Eletrodomésticos", label: "Eletrodomésticos" },
  { id: "Eletrônicos, Áudio e Vídeo", label: "Eletrônicos, Áudio e Vídeo" },
  { id: "Esportes e Fitness", label: "Esportes e Fitness" },
  { id: "Ferramentas", label: "Ferramentas" },
  { id: "Festas e Lembrancinhas", label: "Festas e Lembrancinhas" },
  { id: "Games", label: "Games" },
  { id: "Indústria e Comércio", label: "Indústria e Comércio" },
  { id: "Informática", label: "Informática" },
  { id: "Instrumentos Musicais", label: "Instrumentos Musicais" },
  { id: "Joias e Relógios", label: "Joias e Relógios" },
  { id: "Livros, Revistas e Comics", label: "Livros, Revistas e Comics" },
  { id: "Pet Shop", label: "Pet Shop" },
  { id: "Saúde", label: "Saúde" },
];

function money(value: number | null | undefined) {
  if (value == null) return "";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function stampMs(iso: string | null | undefined) {
  if (!iso) return 0;
  const raw = /Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`;
  const value = new Date(raw).getTime();
  return Number.isFinite(value) ? value : 0;
}

function relative(iso: string | null) {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - stampMs(iso)) / 60000));
  if (mins < 1) return "agora";
  if (mins < 60) return `há ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `há ${hours} h`;
  return `há ${Math.round(hours / 24)} d`;
}

function mergeHub(prev: Opportunity[], incoming: Opportunity[]) {
  const byId = new Map(prev.map((item) => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return [...byId.values()]
    .sort((left, right) => stampMs(right.source_created_at || right.observed_at) - stampMs(left.source_created_at || left.observed_at))
    .slice(0, 400);
}

function reasonsOf(item: Opportunity) {
  return item.reasons ?? [];
}

function categoriesOf(item: Opportunity) {
  const named = reasonsOf(item)
    .filter((reason) => reason.startsWith("hub_cat:"))
    .map((reason) => reason.slice("hub_cat:".length));
  if (named.length) return named;
  if (item.category && item.category !== "hub") return [item.category];
  return [];
}

function isExtra(item: Opportunity) {
  return reasonsOf(item).includes("hub_extra") || /extras/i.test(item.payment_hint || "") || /extras/i.test(item.description || "");
}

function isBest(item: Opportunity) {
  return reasonsOf(item).includes("hub_best");
}

function discountOf(item: Opportunity) {
  if (item.announced_discount_pct != null && item.announced_discount_pct >= 5) {
    return Math.round(item.announced_discount_pct);
  }
  return null;
}

function isFresh(item: Opportunity, minutes = 30) {
  const iso = item.source_created_at || item.observed_at;
  if (!iso) return false;
  return Date.now() - new Date(iso).getTime() < minutes * 60_000;
}

export default function Hub() {
  const [items, setItems] = useState<Opportunity[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hint, setHint] = useState("");
  const [store, setStore] = useState("");
  const [source, setSource] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<"recent" | "discount" | "price">("recent");
  const [saved, setSaved] = useState<Set<string>>(new Set());

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const data = await fetchOpportunities({ source: "mlhub", limit: 400 });
        if (!alive) return;
        setItems((prev) => mergeHub(prev, data.items));
        setTotal(data.total);
        setError(null);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "Erro desconhecido");
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 4000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const hintNeedle = hint.trim().toLowerCase();
    const filtered = items.filter((item) => {
      if (store && store !== "mercadolivre") return false;
      if (source === "extra" && !isExtra(item)) return false;
      if (source === "best" && !isBest(item)) return false;
      if (category && !categoriesOf(item).includes(category)) return false;
      if (needle && !`${item.product} ${categoriesOf(item).join(" ")}`.toLowerCase().includes(needle)) return false;
      if (hintNeedle && !`${item.description ?? ""} ${item.payment_hint ?? ""}`.toLowerCase().includes(hintNeedle)) return false;
      return true;
    });
    if (sort === "recent") return filtered;
    const ranked = [...filtered];
    ranked.sort((left, right) => {
      if (sort === "discount") return (discountOf(right) ?? -1) - (discountOf(left) ?? -1);
      return left.current_price - right.current_price;
    });
    return ranked;
  }, [items, query, hint, store, source, category, sort]);

  const freshCount = items.filter((item) => isFresh(item, 20)).length;

  function countBySource(id: string) {
    if (id === "extra") return items.filter(isExtra).length;
    if (id === "best") return items.filter(isBest).length;
    return items.length;
  }
  function countByCategory(id: string) {
    if (!id) return items.length;
    return items.filter((item) => categoriesOf(item).includes(id)).length;
  }

  function toggleSaved(id: string) {
    setSaved((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function clearFilters() {
    setQuery("");
    setHint("");
    setStore("");
    setSource("");
    setCategory("");
    setSort("recent");
  }

  return (
    <>
      <header className="hero-row">
        <div>
          <h1>Hub agora</h1>
          <p>Destaques do teu painel de afiliado do Mercado Livre.</p>
        </div>
        <div className="pills">
          <span className="pill">
            <b>{total || items.length}</b> destaques hoje
          </span>
          <span className="pill accent">
            <b>{freshCount}</b> novas agora
          </span>
        </div>
      </header>

      <form
        className="search-row"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <label className="search-box">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3-3" />
          </svg>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar produto, loja ou marca"
            aria-label="Buscar produto, loja ou marca"
          />
          <kbd>⌘K</kbd>
        </label>
        <label className="link-box">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 1v22M5 8h14M5 16h14" />
          </svg>
          <input
            value={hint}
            onChange={(event) => setHint(event.target.value)}
            placeholder="Filtrar por ganhos"
            aria-label="Filtrar por ganhos"
          />
        </label>
        <button className="compare" type="button" onClick={clearFilters}>
          Limpar <span>→</span>
        </button>
      </form>
      {error ? <div className="banner">{error}. Suba a API em :8000.</div> : null}

      <div className="stores-row">
        <span className="row-label">Lojas</span>
        <button className={store === "" ? "store-chip on" : "store-chip"} type="button" onClick={() => setStore("")}>
          Todas
        </button>
        <button
          className={`store-chip mercadolivre ${store === "mercadolivre" ? "on" : ""}`}
          type="button"
          onClick={() => setStore("mercadolivre")}
        >
          <i>M</i>
          Mercado Livre
        </button>
      </div>

      <div className="layout">
        <aside className="sidebar">
          <p className="side-title">Fontes</p>
          <button className={source === "" ? "side-item on" : "side-item"} type="button" onClick={() => setSource("")}>
            <span>Todas as fontes</span>
            <b>{items.length}</b>
          </button>
          <button className={source === "extra" ? "side-item on" : "side-item"} type="button" onClick={() => setSource("extra")}>
            <span>Ganhos extras</span>
            <b>{countBySource("extra")}</b>
          </button>
          <button className={source === "best" ? "side-item on" : "side-item"} type="button" onClick={() => setSource("best")}>
            <span>Mais vendidos</span>
            <b>{countBySource("best")}</b>
          </button>

          <p className="side-title">Categorias</p>
          {HUB_CATEGORIES.map((cat) => (
            <button
              key={cat.id || "all"}
              className={category === cat.id ? "side-item on" : "side-item"}
              type="button"
              onClick={() => setCategory(cat.id)}
            >
              <span>{cat.label}</span>
              <b>{countByCategory(cat.id)}</b>
            </button>
          ))}
        </aside>

        <section className="results">
          <div className="results-head">
            <h2>
              {visible.length} oferta{visible.length === 1 ? "" : "s"} encontrada{visible.length === 1 ? "" : "s"}
            </h2>
            <label className="sort">
              Ordenar por
              <select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}>
                <option value="recent">Mais recentes</option>
                <option value="discount">Maior desconto</option>
                <option value="price">Menor preço</option>
              </select>
            </label>
          </div>

          {items.length === 0 ? (
            <div className="empty">
              <h2>Buscando destaques…</h2>
              <p>O coletor está lendo o hub agora. As primeiras peças entram no próximo ciclo.</p>
            </div>
          ) : visible.length === 0 ? (
            <div className="empty">
              <h2>Nenhuma oferta neste filtro</h2>
              <p>Troque a fonte, a loja ou a busca.</p>
            </div>
          ) : (
            <div className="grid">
              {visible.map((item) => {
                const off = discountOf(item);
                const loved = saved.has(item.id);
                return (
                  <article key={item.id} className="deal">
                    <div className="media">
                      {item.image_url ? (
                        <img src={item.image_url} alt="" referrerPolicy="no-referrer" />
                      ) : (
                        <div className="placeholder" />
                      )}
                      {off != null ? <span className="disc">-{off}%</span> : null}
                      <button
                        className={loved ? "heart on" : "heart"}
                        aria-label="Salvar"
                        type="button"
                        onClick={() => toggleSaved(item.id)}
                      >
                        {loved ? "♥" : "♡"}
                      </button>
                    </div>
                    <div className="body">
                      <div className="store-row">
                        <span className="store-name mercadolivre">Mercado Livre</span>
                        {item.price_verified ? <span className="ok">Verificada</span> : null}
                      </div>
                      <h3>{item.product}</h3>
                      <p className="via">{[categoriesOf(item)[0], item.description || "Hub · Destaque"].filter(Boolean).join(" · ")}</p>
                      <p className="price">
                        {item.current_price > 0 ? <strong>{money(item.current_price)}</strong> : <strong>Ver oferta</strong>}
                      </p>
                      {item.payment_hint ? <p className="hint">{item.payment_hint}</p> : null}
                      <div className="foot">
                        <span>{relative(item.source_created_at || item.observed_at)}</span>
                        {item.purchase_url ? (
                          <a href={item.purchase_url} target="_blank" rel="noreferrer">
                            Ver oferta →
                          </a>
                        ) : (
                          <span>Sem link da loja</span>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
