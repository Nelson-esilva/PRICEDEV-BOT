export type PublicDeal = {
  id: string; slug: string; store: string; product: string; merchant: string | null;
  category: string | null; image_url: string | null; description: string | null;
  coupon_code: string | null; payment_hint: string | null; current_price: number;
  list_price: number | null; announced_discount_pct: number | null; discount_pct: number | null;
  discount_basis: 'historical' | 'store' | null; currency: string; go_path: string;
  price_max?: number | null; sales_count?: number | null; rating?: number | null; best_seller?: boolean | null; free_shipping?: boolean | null;
  price_condition?: 'pix' | 'coupon' | null; regular_price?: number | null;
  gallery?: string[] | null; rank_position?: number | null; rank_category?: string | null; rank_category_id?: string | null; trending?: boolean;
  updated_at: string; expires_at: string;
};
export type Promotion = {
  id: string; slug: string; store: string; kind: 'campaign' | 'coupon'; title: string;
  description: string | null; terms: string | null; code: string | null; image_url: string | null;
  starts_at: string | null; expires_at: string | null; updated_at: string; go_path: string;
};
export type List<T> = { items: T[]; total: number };
export type Ranking = { id: string; label: string; count: number; image_url: string | null; top: string };
export type SiteInfo = { telegram_url: string | null; stores: { id: string; label: string; count: number }[] };
export type HomeRanking = Ranking & { items: PublicDeal[] };
export type HomeData = { featured: List<PublicDeal>; trending?: List<PublicDeal>; pix?: List<PublicDeal>; cheap?: List<PublicDeal>;
  free_shipping?: List<PublicDeal>; recent?: List<PublicDeal>; loved?: List<PublicDeal>; under100?: List<PublicDeal>; premium?: List<PublicDeal>; ranking?: HomeRanking | null; telegram_url?: string | null; bestsellers?: List<PublicDeal>; discounts: List<PublicDeal>; campaigns: List<Promotion>; coupons: List<Promotion> };
export const STORE_OPTIONS = [
  { id: 'shopee', label: 'Shopee', mark: 'S', caption: 'Achadinhos para o dia a dia' },
  { id: 'mercadolivre', label: 'Mercado Livre', mark: 'ML', caption: 'Tecnologia, casa e muito mais' },
  { id: 'kabum', label: 'KaBuM!', mark: 'K!', caption: 'Hardware, games e cupons para seu setup' },
  { id: 'amazon', label: 'Amazon', mark: 'a', caption: 'Casa, mercado, eletrônicos e mais' },
];
export const CATEGORIES = [
  { id: 'eletronicos', label: 'Eletrônicos', icon: 'headphones' },
  { id: 'informatica', label: 'Informática', icon: 'monitor' },
  { id: 'celulares', label: 'Celulares', icon: 'phone' },
  { id: 'casa', label: 'Casa & cozinha', icon: 'home' },
  { id: 'moda', label: 'Moda', icon: 'bag' },
  { id: 'beleza', label: 'Beleza', icon: 'sparkles' },
  { id: 'games', label: 'Games', icon: 'game' },
  { id: 'esportes', label: 'Esportes', icon: 'activity' },
  { id: 'infantil', label: 'Infantil', icon: 'gift' },
  { id: 'pets', label: 'Pets', icon: 'heart' },
  { id: 'mercado', label: 'Mercado', icon: 'cart' },
  { id: 'ferramentas', label: 'Ferramentas & auto', icon: 'wrench' },
  { id: 'livros', label: 'Livros & papelaria', icon: 'book' },
];
export function storeLabel(store: string) { return STORE_OPTIONS.find(s => s.id === store)?.label || store; }
export function buyLabel(store: string) { return `Ver na ${storeLabel(store)}`; }
export function money(value: number | null | undefined) { return value == null ? '' : value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }); }
export function soldLabel(n?: number | null) {
  if (!n || n < 1) return '';
  const compact = n >= 1_000_000 ? `${Math.floor(n / 100_000) / 10} mi`.replace('.', ',') : n >= 1000 ? `${Math.floor(n / 1000)} mil` : String(n);
  return `+${compact} vendidos`;
}
export function ratingLabel(n?: number | null) { return n ? n.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : ''; }
// Preço que só vale no Pix ou com cupom ativado: o rótulo junto do preço e o valor sem a condição.
const CONDITIONS = { pix: ['no Pix', 'nos outros meios'], coupon: ['com cupom', 'sem o cupom'] } as const;
export function priceCondition(deal: PublicDeal) {
  if (!deal.price_condition || !(deal.price_condition in CONDITIONS)) return null;
  const [when, otherwise] = CONDITIONS[deal.price_condition];
  return { when, otherwise: deal.regular_price ? `ou ${money(deal.regular_price)} ${otherwise}` : null };
}
export function discountOf(deal: PublicDeal) { const n = deal.discount_pct ?? deal.announced_discount_pct; return n != null && n > 0 && n < 100 ? Math.round(n) : null; }
export function relativeTime(iso?: string | null) {
  if (!iso) return '';
  const n = new Date(iso).getTime(); if (!Number.isFinite(n)) return '';
  const min = Math.max(0, Math.floor((Date.now() - n) / 60000));
  return min < 1 ? 'agora' : min < 60 ? `há ${min} min` : min < 1440 ? `há ${Math.floor(min / 60)} h` : `há ${Math.floor(min / 1440)} d`;
}
export function dateLabel(iso: string | null) { return iso ? new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }) : 'Consulte as regras'; }
// Shopee usa 2999-12-31 para coleções sem prazo.
export function hasDeadline(iso: string | null) { return !!iso && new Date(iso).getFullYear() < 2100; }
export function queryString(values: Record<string, string | number | boolean | undefined | null>) {
  const params = new URLSearchParams(); Object.entries(values).forEach(([k, v]) => { if (v != null && v !== '') params.set(k, String(v)); }); return params.toString();
}
// Ofertas que já vieram em alguma lista: a página do produto abre com elas na hora,
// e a versão atualizada chega em segundo plano.
const seenDeals = new Map<string, PublicDeal>();
export function cachedDeal(slug: string) { return seenDeals.get(slug) || null; }
function remember(value: unknown, depth = 0) {
  if (!value || typeof value !== 'object' || depth > 3) return;
  if (Array.isArray(value)) { value.forEach(item => remember(item, depth + 1)); return; }
  const record = value as Record<string, unknown>;
  if (typeof record.slug === 'string' && typeof record.go_path === 'string' && 'current_price' in record) {
    if (seenDeals.size > 2000) seenDeals.clear();
    seenDeals.set(record.slug, record as unknown as PublicDeal); return;
  }
  Object.values(record).forEach(item => remember(item, depth + 1));
}
export async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/public/v1${path}`, { signal });
  if (!response.ok) throw new Error(response.status === 404 ? 'Esta oferta não está mais disponível.' : 'Não foi possível carregar agora. Tente novamente.');
  const data = await response.json(); remember(data); return data;
}
export function fetchDeals(opts: Record<string, string | number | boolean | undefined> = {}) { return request<List<PublicDeal>>(`/deals?${queryString(opts)}`); }
export async function fetchDeal(slug: string) { try { return await request<PublicDeal>(`/deals/${encodeURIComponent(slug)}`); } catch { return null; } }
