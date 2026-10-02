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
  image_url: string | null;
  description: string | null;
  coupon_code: string | null;
  payment_hint: string | null;
  temperature: number | null;
  free_shipping: boolean | null;
  comment_count: number | null;
  purchase_url: string | null;
  observed_at: string | null;
  source_created_at: string | null;
};

const API = "";

export async function fetchOpportunities(): Promise<{ items: Opportunity[]; total: number }> {
    const params = new URLSearchParams({ limit: "200" });
  const response = await fetch(`${API}/api/v1/opportunities?${params.toString()}`);
  if (!response.ok) throw new Error("Falha ao carregar oportunidades");
  return response.json();
}
