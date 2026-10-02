import { useEffect, useMemo, useState } from "react";
import { fetchOpportunities, type Opportunity } from "./api";

const STORES = [
  { id: "amazon", label: "amazon", test: /amazon/i },
  { id: "shopee", label: "shopee", test: /shopee/i },
  { id: "mercadolivre", label: "mercado livre", test: /mercado\s?livre|mercadolivre/i },
  { id: "magalu", label: "Magalu", test: /magalu|magazine\s?luiza/i },
  { id: "kabum", label: "KaBuM!", test: /kabum/i },
  { id: "netshoes", label: "Netshoes", test: /netshoes/i },
] as const;

const CATEGORIES = [
  { id: "", label: "Tudo" },
  { id: "eletronicos", label: "Eletrônicos", keys: ["fone", "headphone", "monitor", "ssd", "tv", "celular", "bluetooth", "notebook", "caixa som"] },
  { id: "casa", label: "Casa", keys: ["cafeteira", "air fryer", "geladeira", "panela", "casa"] },
  { id: "moda", label: "Moda", keys: ["tênis", "tenis", "camisa", "nike", "roupa"] },
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
  const text = blob(item);
  const known = STORES.find((store) => store.test.test(text));
  if (known) return known.id;
  const merchant = (item.merchant || "outras").trim();
  return merchant.toLowerCase();
}

function storeLabel(item: Opportunity) {
  const known = STORES.find((store) => store.id === storeId(item));
  return known?.label ?? item.merchant ?? "Loja";
}

function discountOf(item: Opportunity) {
  const value = item.historical_discount_pct ?? item.announced_discount_pct;
  if (value == null || value <= 0) return null;
  return Math.round(value);
}

function listPrice(item: Opportunity) {
  if (item.historical_median && item.historical_median > item.current_price) return item.historical_median;
  const pct = item.announced_discount_pct;
  if (pct && pct > 0 && pct < 90) return item.current_price / (1 - pct / 100);
  return null;
}

function categoryOf(item: Opportunity) {
  const name = item.product.toLowerCase();
  return CATEGORIES.find((cat) => cat.keys?.some((key) => name.includes(key)))?.id ?? "";
}

function priceHowto(item: Opportunity) {
  const parts: string[] = [];
  if (item.coupon_code) parts.push(`Cupom ${item.coupon_code}`);
  if (item.payment_hint) parts.push(item.payment_hint);
  return parts.join(" + ");
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

export default function App() {
  const [items, setItems] = useState<Opportunity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [store, setStore] = useState("");
  const [category, setCategory] = useState("");
  const [view, setView] = useState<"ofertas" | "como">("ofertas");
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const data = await fetchOpportunities();
        if (!alive) return;
        setItems(data.items.filter((item) => item.source !== "mock"));
        setRefreshedAt(new Date());
        setError(null);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "Erro desconhecido");
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const tabs = useMemo(() => {
    const extra = new Map<string, string>();
    for (const item of items) {
      const id = storeId(item);
      if (!STORES.some((row) => row.id === id)) extra.set(id, item.merchant || id);
    }
    return [...STORES, ...[...extra.entries()].map(([id, label]) => ({ id, label }))];
  }, [items]);

  const visible = useMemo(() => {
    return items.filter((item) => {
      if (store && storeId(item) !== store) return false;
      if (category && categoryOf(item) !== category) return false;
      return true;
    });
  }, [items, store, category]);

  async function copyCoupon(code: string) {
    await navigator.clipboard.writeText(code);
    setCopied(code);
    window.setTimeout(() => setCopied(null), 1500);
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="logo" href="/" onClick={(e) => { e.preventDefault(); setView("ofertas"); setStore(""); }}>
            price<span>dev</span>.
          </a>
          <nav className="nav">
            <button className={view === "ofertas" ? "on" : ""} onClick={() => { setView("ofertas"); setStore(""); }}>
              Ofertas
            </button>
            <button className={store ? "on" : ""} onClick={() => setView("ofertas")}>
              Lojas
            </button>
            <button className={view === "como" ? "on" : ""} onClick={() => setView("como")}>
              Como funciona
            </button>
          </nav>
          <div className="top-actions">
            <button className="icon-btn" aria-label="Alertas">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8a6 6 0 10-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
                <path d="M13.73 21a2 2 0 01-3.46 0" />
              </svg>
            </button>
            <button className="ghost">Entrar</button>
            <button className="primary">Criar alerta</button>
          </div>
        </div>
        <div className="stores">
          {tabs.map((tab) => (
            <button key={tab.id} className={store === tab.id ? "on" : ""} onClick={() => { setView("ofertas"); setStore(tab.id); }}>
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      <main className="page">
        {error && <div className="banner">{error}. Suba a API em :8000.</div>}

        {view === "como" ? (
          <section className="how" style={{ marginTop: 28 }}>
            <h2>Como funciona</h2>
            <ol>
              <li>Coletamos ofertas de fontes ativas (hoje o Pelando, Shopee quando configurada).</li>
              <li>O preço comunitário não é tratado como preço verificado na loja.</li>
              <li>As abas filtram pela loja anunciada na oferta, não pelo coletor.</li>
            </ol>
          </section>
        ) : (
          <>
            <div className="hero">
              <div>
                <p className="live"><i /> Ao vivo</p>
                <h1>Ofertas quentes agora</h1>
                <p>
                  {refreshedAt
                    ? `Atualizadas ${relative(refreshedAt.toISOString()) || "há poucos segundos"}`
                    : "Carregando…"}
                </p>
              </div>
              <a className="see-all" href="#lista" onClick={() => setStore("")}>
                Ver todas →
              </a>
            </div>

            <div className="cats">
              {CATEGORIES.map((cat) => (
                <button key={cat.id || "all"} className={category === cat.id ? "on" : ""} onClick={() => setCategory(cat.id)}>
                  {cat.label}
                </button>
              ))}
            </div>

            {visible.length === 0 ? (
              <div className="empty">
                <h2>Nenhuma oferta neste filtro</h2>
                <p className="meta">Troque a loja ou a categoria. Novas peças entram quando o coletor achar postagem nova.</p>
              </div>
            ) : (
              <section id="lista" className="grid">
                {visible.map((item) => {
                  const off = discountOf(item);
                  const old = listPrice(item);
                  const loved = saved.has(item.id);
                  return (
                    <article key={item.id} className="deal">
                      <div className="media">
                        {item.image_url ? (
                          <img src={item.image_url} alt="" referrerPolicy="no-referrer" />
                        ) : (
                          <div className="placeholder" />
                        )}
                        {off != null && <span className="disc">-{off}%</span>}
                        <button
                          className={loved ? "heart on" : "heart"}
                          aria-label="Salvar"
                          onClick={() => {
                            setSaved((prev) => {
                              const next = new Set(prev);
                              if (next.has(item.id)) next.delete(item.id);
                              else next.add(item.id);
                              return next;
                            });
                          }}
                        >
                          {loved ? "♥" : "♡"}
                        </button>
                      </div>
                      <div className="body">
                        <div className="store-row">
                          <span>{storeLabel(item)}</span>
                          {item.price_verified ? (
                            <span className="ok">✓ Verificada</span>
                          ) : null}
                        </div>
                        <h3>{item.product}</h3>
                        <p className="price">
                          {item.current_price > 0 ? (
                            <strong>{money(item.current_price)}</strong>
                          ) : item.announced_discount_pct ? (
                            <strong>{Math.round(item.announced_discount_pct)}% OFF</strong>
                          ) : (
                            <strong>Cupom</strong>
                          )}
                          {old != null && <s>{money(old)}</s>}
                        </p>
                        {priceHowto(item) ? (
                          item.coupon_code ? (
                            <button
                              type="button"
                              className="howto"
                              onClick={() => void copyCoupon(item.coupon_code!)}
                            >
                              {copied === item.coupon_code ? "copiado" : priceHowto(item)}
                            </button>
                          ) : (
                            <p className="howto">{priceHowto(item)}</p>
                          )
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
              </section>
            )}
          </>
        )}
      </main>
    </>
  );
}
