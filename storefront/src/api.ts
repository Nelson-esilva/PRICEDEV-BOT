export type PublicDeal = {
  id: string;
  slug: string;
  store: string;
  product: string;
  merchant: string | null;
  category: string | null;
  image_url: string | null;
  description: string | null;
  coupon_code: string | null;
  payment_hint: string | null;
  current_price: number;
  list_price: number | null;
  announced_discount_pct: number | null;
  currency: string;
  go_path: string;
  updated_at: string;
  expires_at: string;
};

const STORES: Record<string, string> = {
  shopee: "Shopee",
  mercadolivre: "Mercado Livre",
};

export const STORE_OPTIONS = [
  { id: "", label: "Todas as lojas" },
  { id: "shopee", label: "Shopee" },
  { id: "mercadolivre", label: "Mercado Livre" },
];

export const CATEGORIES = [
  { id: "", label: "Tudo" },
  { id: "eletronicos", label: "Eletrônicos" },
  { id: "casa", label: "Casa" },
  { id: "moda", label: "Moda" },
  { id: "beleza", label: "Beleza" },
  { id: "games", label: "Games" },
];

export function storeLabel(store: string) {
  return STORES[store] || store;
}

export function buyLabel(store: string) {
  if (store === "shopee") return "Comprar na Shopee";
  if (store === "mercadolivre") return "Comprar no Mercado Livre";
  return `Comprar na ${storeLabel(store)}`;
}

function withParams(opts: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(opts)) {
    if (value == null) continue;
    const text = String(value).trim();
    if (text) params.set(key, text);
  }
  return params;
}

export async function fetchDeals(opts: {
  q?: string;
  store?: string;
  category?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ items: PublicDeal[]; total: number }> {
  const params = withParams({
    q: opts.q,
    store: opts.store,
    category: opts.category,
    limit: opts.limit ?? 48,
    offset: opts.offset ?? 0,
  });
  const response = await fetch(`/api/public/v1/deals?${params.toString()}`);
  if (!response.ok) throw new Error("Falha ao carregar ofertas");
  return response.json();
}

export async function fetchDeal(slug: string): Promise<PublicDeal | null> {
  const response = await fetch(`/api/public/v1/deals/${encodeURIComponent(slug)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("Falha ao carregar a oferta");
  return response.json();
}

export function money(value: number | null | undefined) {
  if (value == null) return "";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function discountOf(deal: PublicDeal): number | null {
  if (deal.announced_discount_pct != null && deal.announced_discount_pct >= 5) {
    return Math.round(deal.announced_discount_pct);
  }
  if (deal.list_price != null && deal.list_price > deal.current_price) {
    return Math.round((1 - deal.current_price / deal.list_price) * 100);
  }
  return null;
}

export function relativeTime(iso: string | null | undefined) {
  if (!iso) return "";
  const raw = /Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`;
  const then = new Date(raw).getTime();
  if (!Number.isFinite(then)) return "";
  const delta = Math.max(0, Date.now() - then);
  const minutes = Math.round(delta / 60000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.round(hours / 24);
  return `há ${days} d`;
}
