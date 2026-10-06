import { useEffect, useMemo, useState } from "react";
import { fetchInbox, type InboxItem } from "./api";
import Pager from "./Pager";

const STORES = [
  { id: "mercadolivre", label: "Mercado Livre", letter: "M" },
  { id: "amazon", label: "Amazon", letter: "A" },
  { id: "shopee", label: "Shopee", letter: "S" },
  { id: "magalu", label: "Magazine Luiza", letter: "M" },
  { id: "kabum", label: "Kabum!", letter: "K" },
  { id: "netshoes", label: "Netshoes", letter: "N" },
  { id: "afiliado", label: "Afiliado", letter: "A" },
] as const;

const CATEGORIES = [
  { id: "", label: "Tudo" },
  { id: "eletronicos", label: "Eletrônicos", keys: ["fone", "headphone", "monitor", "ssd", "tv", "celular", "bluetooth", "notebook", "caixa som"] },
  { id: "casa", label: "Casa", keys: ["cafeteira", "air fryer", "geladeira", "panela", "casa", "espresso"] },
  { id: "moda", label: "Moda", keys: ["tênis", "tenis", "camisa", "nike", "roupa", "calça"] },
  { id: "beleza", label: "Beleza", keys: ["creme", "sérum", "serum", "shampoo", "refil", "desodorante", "gel"] },
  { id: "games", label: "Games", keys: ["game", "playstation", "xbox", "nintendo"] },
];

const STORE_LABEL: Record<string, string> = Object.fromEntries(STORES.map((store) => [store.id, store.label]));

function postedMs(iso: string | null) {
  if (!iso) return 0;
  const raw = /Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`;
  const value = new Date(raw).getTime();
  return Number.isFinite(value) ? value : 0;
}

function relative(iso: string | null) {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - postedMs(iso)) / 60000));
  if (mins < 1) return "agora";
  if (mins < 60) return `há ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `há ${hours} h`;
  return `há ${Math.round(hours / 24)} d`;
}

function money(value: number | null | undefined) {
  if (value == null) return "";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

const PAGE_SIZE = 48;

function categoryOf(item: InboxItem) {
  const name = item.product.toLowerCase();
  return CATEGORIES.find((cat) => cat.keys?.some((key) => name.includes(key)))?.id ?? "";
}

export default function Inbox() {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [total, setTotal] = useState(0);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [store, setStore] = useState("");
  const [source, setSource] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<"recent" | "price">("recent");
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [broken, setBroken] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [query, store, source, category]);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const data = await fetchInbox({
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
          q: query,
          marketplace: store,
          chat: source,
          category,
        });
        if (!alive) return;
        setItems(data.items);
        setTotal(data.total);
        setListening(data.listening);
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
  }, [page, query, store, source, category]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const groups = useMemo(() => {
    const names = new Set(items.map((item) => item.chat_title).filter(Boolean));
    return [...names].sort((left, right) => left.localeCompare(right, "pt"));
  }, [items]);

  const storeTabs = useMemo(() => {
    const present = new Set(items.map((item) => item.marketplace));
    return STORES.filter((tab) => present.has(tab.id));
  }, [items]);

  const visible = useMemo(() => {
    if (sort === "recent") return items;
    return [...items].sort((left, right) => (left.price ?? 1e12) - (right.price ?? 1e12));
  }, [items, sort]);

  function countByGroup(name: string) {
    return items.filter((item) => item.chat_title === name).length;
  }
  function countByCategory(id: string) {
    if (!id) return items.length;
    return items.filter((item) => categoryOf(item) === id).length;
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
    setStore("");
    setSource("");
    setCategory("");
    setSort("recent");
  }

  return (
    <>
      <header className="hero-row">
        <div>
          <h1>Canais agora</h1>
          <p>Promoções que aparecem nos grupos de Telegram em que você já está.</p>
        </div>
        <div className="pills">
          <span className="pill">
            <b>{total || items.length}</b> posts hoje
          </span>
          <span className={`pill ${listening ? "accent" : ""}`}>
            <b>{listening ? "ligada" : "off"}</b> escuta
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
        {(storeTabs.length ? storeTabs : STORES).map((tab) => (
          <button
            key={tab.id}
            className={`store-chip ${tab.id} ${store === tab.id ? "on" : ""}`}
            type="button"
            onClick={() => setStore(tab.id)}
          >
            <i>{tab.letter}</i>
            {tab.label}
          </button>
        ))}
      </div>

      <div className="layout">
        <aside className="sidebar">
          <p className="side-title">Fontes</p>
          <button className={source === "" ? "side-item on" : "side-item"} type="button" onClick={() => setSource("")}>
            <span>Todos os grupos</span>
            <b>{total}</b>
          </button>
          {groups.map((name) => (
            <button key={name} className={source === name ? "side-item on" : "side-item"} type="button" onClick={() => setSource(name)}>
              <span>{name}</span>
              <b>{countByGroup(name)}</b>
            </button>
          ))}

          <p className="side-title">Categorias</p>
          {CATEGORIES.map((cat) => (
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
              {total} post{total === 1 ? "" : "s"} no banco
            </h2>
            <label className="sort">
              Ordenar por
              <select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}>
                <option value="recent">Mais recentes</option>
                <option value="price">Menor preço</option>
              </select>
            </label>
          </div>

          {items.length === 0 && !(query.trim() || store || source || category) ? (
            <div className="empty">
              <h2>{listening ? "Esperando o próximo post…" : "Escuta desligada"}</h2>
              <p>
                {listening
                  ? "Quando alguém mandar um link de loja no grupo, o card entra aqui."
                  : "Crie o app em my.telegram.org, rode python -m app.inbox.login e ligue ENABLE_CHANNEL_INBOX."}
              </p>
            </div>
          ) : visible.length === 0 ? (
            <div className="empty">
              <h2>Nenhuma oferta neste filtro</h2>
              <p>Troque a fonte, a loja ou a busca.</p>
            </div>
          ) : (
            <div className="grid">
              {visible.map((item) => {
                const loved = saved.has(item.id);
                const off =
                  item.listed_price != null && item.price != null && item.listed_price > item.price
                    ? Math.round(((item.listed_price - item.price) / item.listed_price) * 100)
                    : null;
                return (
                  <article key={item.id} className="deal">
                    <div className="media">
                      {item.image_url && !broken.has(item.id) ? (
                        <img
                          src={item.image_url}
                          alt=""
                          referrerPolicy="no-referrer"
                          onError={() =>
                            setBroken((prev) => {
                              const next = new Set(prev);
                              next.add(item.id);
                              return next;
                            })
                          }
                        />
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
                        <span className={`store-name ${item.marketplace}`}>
                          {STORE_LABEL[item.marketplace] || item.marketplace}
                        </span>
                        <span className="ok">{item.stamped ? "Afiliado" : "Grupo"}</span>
                      </div>
                      <h3>{item.product}</h3>
                      <p className="via">Telegram · {item.chat_title || "grupo"}</p>
                      <p className="price">
                        {item.price != null ? (
                          <strong>{money(item.price)}</strong>
                        ) : (
                          <strong>Ver oferta</strong>
                        )}
                        {item.listed_price != null && item.price != null && item.listed_price > item.price ? (
                          <s>{money(item.listed_price)}</s>
                        ) : null}
                      </p>
                      {item.coupon_code ? (
                        <div className="coupon">
                          <span>
                            Cupom <b>{item.coupon_code}</b>
                          </span>
                        </div>
                      ) : item.payment_hint ? (
                        <p className="hint">{item.payment_hint}</p>
                      ) : null}
                      <div className="foot">
                        <span>{relative(item.posted_at)}</span>
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
          <Pager page={page} pageCount={pageCount} total={total} pageSize={PAGE_SIZE} onPage={setPage} />
        </section>
      </div>
    </>
  );
}
