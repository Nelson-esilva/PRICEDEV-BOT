export type PublicDeal = {
  id: string; slug: string; store: string; product: string; merchant: string | null;
  category: string | null; image_url: string | null; description: string | null;
  coupon_code: string | null; payment_hint: string | null; current_price: number;
  list_price: number | null; announced_discount_pct: number | null; discount_pct: number | null;
  discount_basis: 'historical' | 'store' | null; currency: string; go_path: string;
  updated_at: string; expires_at: string;
};
export type Promotion = {
  id: string; slug: string; store: string; kind: 'campaign' | 'coupon'; title: string;
  description: string | null; terms: string | null; code: string | null; image_url: string | null;
  starts_at: string | null; expires_at: string | null; updated_at: string; go_path: string;
};
export type List<T> = { items: T[]; total: number };
export type HomeData = { featured: List<PublicDeal>; discounts: List<PublicDeal>; campaigns: List<Promotion>; coupons: List<Promotion> };
export const STORE_OPTIONS = [
  { id: 'shopee', label: 'Shopee', mark: 'S', caption: 'Achadinhos para o dia a dia' },
  { id: 'mercadolivre', label: 'Mercado Livre', mark: 'ML', caption: 'Tecnologia, casa e muito mais' },
  { id: 'kabum', label: 'KaBuM!', mark: 'K!', caption: 'Campanhas e cupons para seu setup' },
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
];
export function storeLabel(store: string) { return STORE_OPTIONS.find(s => s.id === store)?.label || store; }
export function buyLabel(store: string) { return `Ver na ${storeLabel(store)}`; }
export function money(value: number | null | undefined) { return value == null ? '' : value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }); }
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
export async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/public/v1${path}`, { signal });
  if (!response.ok) throw new Error(response.status === 404 ? 'Esta oferta não está mais disponível.' : 'Não foi possível carregar agora. Tente novamente.');
  return response.json();
}
export function fetchDeals(opts: Record<string, string | number | boolean | undefined> = {}) { return request<List<PublicDeal>>(`/deals?${queryString(opts)}`); }
export async function fetchDeal(slug: string) { try { return await request<PublicDeal>(`/deals/${encodeURIComponent(slug)}`); } catch { return null; } }
