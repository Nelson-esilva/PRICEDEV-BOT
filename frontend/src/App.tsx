import { useEffect, useMemo, useState, type FormEvent } from "react";
import { addWatch, fetchOpportunities, type Opportunity } from "./api";
import Hub from "./Hub";
import Inbox from "./Inbox";
import Pager from "./Pager";

const STORES = [
  { id: "amazon", label: "Amazon", letter: "A", test: /amazon/i },
  { id: "mercadolivre", label: "Mercado Livre", letter: "M", test: /mercado\s?livre|mercadolivre/i },
  { id: "shopee", label: "Shopee", letter: "S", test: /shopee/i },
  { id: "magalu", label: "Magazine Luiza", letter: "M", test: /magalu|magazine\s?luiza/i },
  { id: "kabum", label: "Kabum!", letter: "K", test: /kabum/i },
  { id: "netshoes", label: "Netshoes", letter: "N", test: /netshoes/i },
] as const;

const SOURCES: Record<string, { label: string; hint: string; tone: "community" | "official" | "affiliate" }> = {
  pelando: { label: "Pelando", hint: "Comunidade", tone: "community" },
  mercadolivre: { label: "Mercado Livre", hint: "Loja oficial", tone: "official" },
  magalu: { label: "Magalu", hint: "Loja oficial", tone: "official" },
  kabum: { label: "KaBuM!", hint: "Loja oficial", tone: "official" },
  shopee: { label: "Shopee", hint: "Afiliados", tone: "affiliate" },
  lomadee: { label: "Lomadee", hint: "Afiliados", tone: "affiliate" },
  watchlist: { label: "Comparar", hint: "Link colado", tone: "official" },
};

const SOURCE_ORDER = ["pelando", "mercadolivre", "kabum", "magalu", "shopee", "lomadee", "watchlist"];

const CATEGORIES = [
  { id: "", label: "Tudo" },
  { id: "eletronicos", label: "Eletrônicos", keys: ["fone", "headphone", "monitor", "ssd", "tv", "celular", "bluetooth", "notebook", "caixa som"] },
  { id: "casa", label: "Casa", keys: ["cafeteira", "air fryer", "geladeira", "panela", "casa", "espresso"] },
  { id: "moda", label: "Moda", keys: ["tênis", "tenis", "camisa", "nike", "roupa", "calça"] },
  { id: "beleza", label: "Beleza", keys: ["creme", "sérum", "serum", "shampoo", "refil", "desodorante", "gel"] },
  { id: "games", label: "Games", keys: ["game", "playstation", "xbox", "nintendo"] },
];

function money(value: number | null | undefined) {
  if (value == null) return "";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function blob(item: Opportunity) {
  return `${item.merchant ?? ""} ${item.purchase_url ?? ""} ${item.source}`;
}

function storeId(item: Opportunity) {
  const known = STORES.find((store) => store.test.test(blob(item)));
  if (known) return known.id;
  return (item.merchant || "outras").trim().toLowerCase();
}

function storeMeta(item: Opportunity) {
  const id = storeId(item);
  const known = STORES.find((store) => store.id === id);
  if (known) return known;
  const label = item.merchant || "Loja";
  return { id, label, letter: label.slice(0, 1).toUpperCase(), test: /$/ };
}

function sourceMeta(source: string) {
  return SOURCES[source] ?? { label: source, hint: "Fonte adicional", tone: "affiliate" as const };
}

function discountOf(item: Opportunity) {
  if (item.announced_discount_pct != null && item.announced_discount_pct >= 5) {
    return Math.round(item.announced_discount_pct);
  }
  if (item.historical_discount_pct != null && item.historical_discount_pct > 0 && (item.history_observations ?? 0) >= 5) {
    return Math.round(item.historical_discount_pct);
  }
  return null;
}

function listPrice(item: Opportunity) {
  if (item.historical_median && item.historical_median > item.current_price) return item.historical_median;
  return null;
}

function categoryOf(item: Opportunity) {
  const name = item.product.toLowerCase();
  return CATEGORIES.find((cat) => cat.keys?.some((key) => name.includes(key)))?.id ?? "";
}

function relative(iso: string | null) {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "agora";
  if (mins < 60) return `há ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `há ${hours} h`;
  return `há ${Math.round(hours / 24)} d`;
}

const PAGE_SIZE = 48;

const VIA_LABEL: Record<string, string> = {
  ofertas: "Ofertas",
  relampago: "Oferta relâmpago",
  "mais-vendidos": "Mais vendidos",
};

function sourceLine(item: Opportunity) {
  const source = sourceMeta(item.source).label;
  const mapped = VIA_LABEL[item.category || ""];
  const kabum =
    item.source === "kabum" && item.category
      ? (item.category.split("/").pop() || item.category).replace(/-/g, " ")
      : "";
  const via = mapped || kabum;
  return via ? `${source} · ${via}` : source;
}

function isFresh(item: Opportunity, minutes = 30) {
  const iso = item.source_created_at || item.observed_at;
  if (!iso) return false;
  return Date.now() - new Date(iso).getTime() < minutes * 60_000;
}

export default function App() {
  const [items, setItems] = useState<Opportunity[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [store, setStore] = useState("");
  const [source, setSource] = useState("");
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"recent" | "discount" | "price">("recent");
  const [help, setHelp] = useState(false);
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState<string | null>(null);
  const [watchUrl, setWatchUrl] = useState("");
  const [watchNote, setWatchNote] = useState<string | null>(null);
  const [moreStores, setMoreStores] = useState(false);
  const [area, setArea] = useState<"ofertas" | "canais" | "hub">("ofertas");
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [source, query, store, category]);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const data = await fetchOpportunities({
          source: source || undefined,
          q: query,
          store: store || undefined,
          category: category || undefined,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
        });
        if (!alive) return;
        setItems(data.items.filter((item) => item.source !== "mock" && item.source !== "mlhub"));
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
  }, [page, source, query, store, category]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const extraStores = useMemo(() => {
    const extra = new Map<string, string>();
    for (const item of items) {
      const id = storeId(item);
      if (!STORES.some((row) => row.id === id)) extra.set(id, item.merchant || id);
    }
    return [...extra.entries()].map(([id, label]) => ({
      id,
      label,
      letter: label.slice(0, 1).toUpperCase(),
    }));
  }, [items]);

  const storeTabs = moreStores ? [...STORES, ...extraStores] : [...STORES];

  const sourceTabs = useMemo(() => {
    const present = new Set(items.map((item) => item.source));
    const known = SOURCE_ORDER.filter((id) => present.has(id));
    const extra = [...present].filter((id) => !SOURCE_ORDER.includes(id));
    return [...known, ...extra];
  }, [items]);

  const visible = useMemo(() => {
    if (sort === "recent") return items;
    const ranked = [...items];
    ranked.sort((a, b) => {
      if (sort === "discount") return (discountOf(b) ?? -1) - (discountOf(a) ?? -1);
      return a.current_price - b.current_price;
    });
    return ranked;
  }, [items, sort]);

  const freshCount = items.filter((item) => isFresh(item, 20)).length;

  function countBySource(id: string) {
    return items.filter((item) => item.source === id).length;
  }
  function countByCategory(id: string) {
    if (!id) return items.length;
    return items.filter((item) => categoryOf(item) === id).length;
  }

  async function copyCoupon(code: string) {
    await navigator.clipboard.writeText(code);
    setCopied(code);
    window.setTimeout(() => setCopied(null), 1500);
  }

  async function followLink(event: FormEvent) {
    event.preventDefault();
    const url = watchUrl.trim();
    if (!url) return;
    try {
      const row = await addWatch(url);
      setWatchNote(`Acompanhando ${row.marketplace}. O preço entra na vitrine no próximo ciclo.`);
      setWatchUrl("");
    } catch (err) {
      setWatchNote(err instanceof Error ? err.message : "Não deu para acompanhar esse link");
    }
  }

  function toggleSaved(id: string) {
    setSaved((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="shell">
      <nav className="area-tabs" aria-label="Áreas">
        <button type="button" className={area === "ofertas" ? "on" : ""} onClick={() => setArea("ofertas")}>
          Ofertas
        </button>
        <button type="button" className={area === "canais" ? "on" : ""} onClick={() => setArea("canais")}>
          Canais
        </button>
        <button type="button" className={area === "hub" ? "on" : ""} onClick={() => setArea("hub")}>
          Hub
        </button>
      </nav>
      {area === "canais" ? <Inbox /> : null}
      {area === "hub" ? <Hub /> : null}
      {area === "ofertas" ? (
        <>
      <header className="hero-row">
        <div>
          <h1>Ofertas agora</h1>
          <p>Preços e cupons encontrados nas principais lojas e comunidades.</p>
        </div>
        <div className="pills">
          <span className="pill">
            <b>{total || items.length}</b> ofertas hoje
          </span>
          <span className="pill accent">
            <b>{freshCount}</b> novas agora
          </span>
        </div>
      </header>

      <form className="search-row" onSubmit={(event) => void followLink(event)}>
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
            <path d="M10 13a5 5 0 007.07 0l1.41-1.41a5 5 0 00-7.07-7.07L10 5.93" />
            <path d="M14 11a5 5 0 00-7.07 0L5.5 12.41a5 5 0 007.07 7.07L14 18.07" />
          </svg>
          <input
            value={watchUrl}
            onChange={(event) => setWatchUrl(event.target.value)}
            placeholder="Cole um link para comparar o preço"
            aria-label="Link para comparar o preço"
          />
        </label>
        <button className="compare" type="submit">
          Comparar <span>→</span>
        </button>
      </form>
      {watchNote ? <p className="watch-note">{watchNote}</p> : null}
      {error ? <div className="banner">{error}. Suba a API em :8000.</div> : null}

      <div className="stores-row">
        <span className="row-label">Lojas</span>
        <button className={store === "" ? "store-chip on" : "store-chip"} onClick={() => setStore("")}>
          Todas
        </button>
        {storeTabs.map((tab) => (
          <button
            key={tab.id}
            className={`store-chip ${tab.id} ${store === tab.id ? "on" : ""}`}
            onClick={() => setStore(tab.id)}
          >
            <i>{tab.letter}</i>
            {tab.label}
          </button>
        ))}
        {extraStores.length > 0 ? (
          <button className="more-stores" type="button" onClick={() => setMoreStores((value) => !value)}>
            {moreStores ? "Menos lojas" : "Mais lojas"} <span>›</span>
          </button>
        ) : null}
      </div>

      <div className="layout">
        <aside className="sidebar">
          <p className="side-title">Fontes</p>
          <button className={source === "" ? "side-item on" : "side-item"} onClick={() => setSource("")}>
            <span>Todas as fontes</span>
            <b>{total}</b>
          </button>
          {sourceTabs.map((id) => (
            <button key={id} className={source === id ? "side-item on" : "side-item"} onClick={() => setSource(id)}>
              <span>{sourceMeta(id).label}</span>
              <b>{countBySource(id)}</b>
            </button>
          ))}

          <p className="side-title">Categorias</p>
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id || "all"}
              className={category === cat.id ? "side-item on" : "side-item"}
              onClick={() => setCategory(cat.id)}
            >
              <span>{cat.label}</span>
              <b>{countByCategory(cat.id)}</b>
            </button>
          ))}
          <button className="help-link" type="button" onClick={() => setHelp((value) => !value)}>
            Como funciona
          </button>
        </aside>

        <section className="results">
          {help ? (
            <div className="how">
              <h2>Como funciona</h2>
              <ol>
                <li>A coluna da esquerda filtra a origem do dado: comunidade, loja oficial, afiliado ou link que você colou.</li>
                <li>O preço riscado só aparece com mediana histórica. O percentual laranja pode ser o desconto anunciado pela loja.</li>
                <li>Selo “Verificada” é preço lido na loja ou no JSON da página, não voto da comunidade.</li>
              </ol>
            </div>
          ) : null}

          <div className="results-head">
            <h2>
              {total} oferta{total === 1 ? "" : "s"} no banco
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

          {items.length === 0 && !(query.trim() || store || source || category) ? (
            <div className="empty">
              <h2>Buscando ofertas…</h2>
              <p>O coletor está lendo as fontes agora. As primeiras peças entram em alguns segundos.</p>
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
                const old = listPrice(item);
                const store = storeMeta(item);
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
                        <span className={`store-name ${store.id}`}>{store.label}</span>
                        {item.price_verified ? <span className="ok">Verificada</span> : null}
                      </div>
                      <h3>{item.product}</h3>
                      <p className="via">{sourceLine(item)}</p>
                      <p className="price">
                        {item.current_price > 0 ? (
                          <strong>{money(item.current_price)}</strong>
                        ) : item.announced_discount_pct ? (
                          <strong>{Math.round(item.announced_discount_pct)}% OFF</strong>
                        ) : (
                          <strong>Cupom</strong>
                        )}
                        {old != null ? <s>{money(old)}</s> : null}
                      </p>
                      {item.coupon_code ? (
                        <div className="coupon">
                          <span>
                            Cupom <b>{item.coupon_code}</b>
                          </span>
                          <button type="button" onClick={() => void copyCoupon(item.coupon_code!)}>
                            {copied === item.coupon_code ? "copiado" : "copiar"}
                          </button>
                        </div>
                      ) : item.payment_hint ? (
                        <p className="hint">{item.payment_hint}</p>
                      ) : null}
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
          <Pager page={page} pageCount={pageCount} total={total} pageSize={PAGE_SIZE} onPage={setPage} />
        </section>
      </div>
        </>
      ) : null}
    </div>
  );
}
