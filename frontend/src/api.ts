export type Opportunity = {
  id: string;
  product_id: string;
  product: string;
  merchant: string | null;
  source: string;
  current_price: number;
  currency: string;
  historical_median: number | null;
  historical_minimum: number | null;
  historical_discount_pct: number | null;
  announced_discount_pct: number | null;
  acceptance_score: number;
    classification: string;
    status: string;
    price_verified: boolean;
    history_confidence?: string;
    history_observations?: number;
    risks?: string[];
  image_url: string | null;
  description: string | null;
  coupon_code: string | null;
  payment_hint: string | null;
  temperature: number | null;
  free_shipping: boolean | null;
  comment_count: number | null;
  purchase_url: string | null;
  category?: string | null;
  description?: string | null;
  observed_at: string | null;
  source_created_at: string | null;
  reasons?: string[];
};

const API = "";

export async function fetchOpportunities(
  opts: { source?: string; limit?: number } = {},
): Promise<{ items: Opportunity[]; total: number }> {
  const params = new URLSearchParams({ limit: String(opts.limit ?? 300) });
  if (opts.source) params.set("source", opts.source);
  const response = await fetch(`${API}/api/v1/opportunities?${params.toString()}`);
  if (!response.ok) throw new Error("Falha ao carregar oportunidades");
  return response.json();
}

export type WatchItem = {
  id: string;
  url: string;
  marketplace: string;
  product_name: string | null;
  last_price: number | null;
  enabled: boolean;
  last_error: string | null;
};

export type InboxItem = {
  id: string;
  channel: string;
  chat_title: string;
  product: string;
  body: string | null;
  purchase_url: string | null;
  marketplace: string;
  image_url?: string | null;
  stamped?: boolean;
  price?: number | null;
  listed_price?: number | null;
  coupon_code?: string | null;
  payment_hint?: string | null;
  posted_at: string;
  received_at: string;
};

export async function fetchInbox(): Promise<{ items: InboxItem[]; total: number; listening: boolean }> {
  const response = await fetch(`${API}/api/v1/inbox?limit=120`);
  if (!response.ok) throw new Error("Falha ao carregar os canais");
  return response.json();
}

export async function addWatch(url: string): Promise<WatchItem> {
  const response = await fetch(`${API}/api/v1/watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) throw new Error("Link inválido ou recusado");
  return response.json();
}
