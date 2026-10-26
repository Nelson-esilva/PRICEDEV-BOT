import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { request, storeLabel, type PublicDeal } from './api';

const paths: Record<string, ReactNode> = {
  search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
  heart: <path d="M20.8 4.7a5.5 5.5 0 0 0-7.8 0L12 5.8l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.5a5.5 5.5 0 0 0 0-7.8Z"/>,
  tag: <><path d="M20 13 12 21 3 12V3h9l8 8a1.5 1.5 0 0 1 0 2Z"/><circle cx="7.5" cy="7.5" r="1"/></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  home: <><path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/></>,
  ticket: <><path d="M3 5h18v5a2 2 0 0 0 0 4v5H3v-5a2 2 0 0 0 0-4Z"/><path d="M15 5v3m0 3v2m0 3v3"/></>,
  bolt: <path d="m13 2-9 12h7l-1 8 10-13h-7Z"/>,
  truck: <><path d="M3 6h11v10H3zM14 9h4l3 3v4h-7"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/></>,
  flame: <path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.2 1.2-3.6 2.2-4.6.2 1.6 1 2.6 2 3 0-3 .3-5.6.8-8.4Z"/>,
  trophy: <><path d="M8 4h8v5a4 4 0 0 1-8 0V4ZM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8.5 20h7M10 17h4v3h-4z"/></>,
  close: <path d="m6 6 12 12M6 18 18 6"/>,
  filter: <><path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="9" cy="18" r="2"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  share: <><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m9 10 6-3m-6 7 6 3"/></>,
  copy: <><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/></>,
  star: <path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z"/>,
  pause: <path d="M8 5v14M16 5v14"/>,
  play: <path d="M7 4.5v15L19 12Z"/>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  monitor: <><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/></>,
  phone: <><rect x="6" y="2" width="12" height="20" rx="3"/><path d="M10 18h4"/></>,
  headphones: <><path d="M3 14v-3a9 9 0 0 1 18 0v3"/><rect x="2" y="12" width="5" height="8" rx="2"/><rect x="17" y="12" width="5" height="8" rx="2"/></>,
  bag: <><path d="M4 7h16l1 14H3Z"/><path d="M8 9V6a4 4 0 0 1 8 0v3"/></>,
  sparkles: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/><path d="M20 2v4m-2-2h4"/></>,
  game: <><path d="M7 6h10c3 0 5 12 3 13s-5-4-5-4H9s-3 5-5 4S4 6 7 6Z"/><path d="M8 9v6m-3-3h6m5-2h1m1 3h1"/></>,
  activity: <path d="M2 12h5l3-9 4 18 3-9h5"/>,
  gift: <><rect x="3" y="8" width="18" height="4"/><path d="M5 12v9h14v-9M12 8v13"/><path d="M12 8S4 8 5 4s7 4 7 4 6-8 7-4-7 4-7 4Z"/></>,
  chevron: <path d="m9 5 7 7-7 7"/>,
  menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
  cart: <><path d="M3 4h2l2.4 11h11l2-8H6.2"/><circle cx="9" cy="19.5" r="1.5"/><circle cx="17" cy="19.5" r="1.5"/></>,
  wrench: <path d="M14.7 6.3a4 4 0 0 0 5 5L21 13l-8 8-3-3 8-8-1.3-1.3a4 4 0 0 1-5-5L9 6l-1 4-4 1 2.6-2.6"/>,
  book: <><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2Z"/><path d="M4 19V5M8 7h7"/></>,
  back: <path d="m15 5-7 7 7 7"/>,
  external: <><path d="M14 3h7v7m0-7L10 14"/><path d="M10 3H3v18h18v-7"/></>,
};
export function Icon({ name, size = 20, ...props }: { name: string; size?: number; className?: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.tag}</svg>;
}
export function Brand({ size = 32 }: { size?: number }) {
  return <span className="brand-lockup"><svg className="brand-mark" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true"><path d="M6 8a4 4 0 0 1 4-4h12.3a4 4 0 0 1 2.8 1.2l10.7 10.7a4 4 0 0 1 0 5.6L23.5 33.8a4 4 0 0 1-5.6 0L7.2 23.1A4 4 0 0 1 6 20.3Z"/><circle cx="14" cy="12" r="2.6"/><path d="m17.5 19.5-3 3 3 3m6-6 3 3-3 3"/></svg><span className="brand-word">Promo<b>Dev</b></span></span>;
}
// Logo do Telegram (preenchido; o Icon é só traço).
export function TelegramIcon({ size = 24, className }: { size?: number; className?: string }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M21.5 4.2 2.9 11.4c-1.3.5-1.3 1.2-.2 1.6l4.8 1.5 1.8 5.6c.2.6.4.8.9.8.4 0 .6-.2.9-.5l2.3-2.2 4.7 3.5c.9.5 1.5.2 1.7-.8L22.9 5.6c.3-1.3-.5-1.9-1.4-1.4ZM8.6 14.1l9.9-6.2c.5-.3.9-.1.5.2l-8.1 7.3-.3 3.4-2-4.7Z"/></svg>;
}
export function StoreTag({ store, extra }: { store: string; extra?: string }) {
  return <span className="store-tag"><i className={`store-dot ${store}`}/>{storeLabel(store)}{extra && <> · {extra}</>}</span>;
}
export function useTitle(title: string) { useEffect(() => {
  document.title = `${title} · PromoDev`;
  document.querySelector('meta[name="description"]')?.setAttribute('content', `${title}. Explore ofertas, campanhas e cupons no PromoDev e confira as condições na loja de origem.`);
}, [title]); }
export function useRemote<T>(path: string | null, initial: T | null = null) {
  const [state, setState] = useState<{ data: T | null; error: string; loading: boolean }>({ data: initial, error: '', loading: true });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!path) { setState({ data: null, error: '', loading: false }); return; }
    const controller = new AbortController();
    setState(s => ({ ...s, loading: true, error: '' }));
    request<T>(path, controller.signal).then(data => setState({ data, loading: false, error: '' })).catch(error => {
      if (!controller.signal.aborted) setState({ data: null, loading: false, error: error.message });
    });
    return () => controller.abort();
  }, [path, attempt]);
  return { ...state, retry: () => setAttempt(n => n + 1) };
}
const SavedContext = createContext<{ saved: PublicDeal[]; toggle: (d: PublicDeal) => void }>({ saved: [], toggle: () => {} });
// Vistos recentemente: só ids no navegador; a home busca preço e disponibilidade atuais.
const RECENT_KEY = 'promodev-recent-v1';
export function recordView(id: string) {
  try {
    const old: string[] = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
    localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...(Array.isArray(old) ? old : []).filter(x => x !== id)].slice(0, 24)));
  } catch { /* sem armazenamento: a linha só não aparece */ }
}
export function recentIds(): string[] {
  try { const value = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); return Array.isArray(value) ? value.filter(x => typeof x === 'string') : []; } catch { return []; }
}
export function SavedProvider({ children }: { children: ReactNode }) {
  const [saved, setSaved] = useState<PublicDeal[]>(() => {
    try { const value = JSON.parse(localStorage.getItem('promodev-saved-v1') || '[]'); return Array.isArray(value) ? value.filter(d => d?.id && d?.slug).slice(0, 100) : []; } catch { return []; }
  });
  function toggle(deal: PublicDeal) {
    setSaved(old => { const next = old.some(d => d.id === deal.id) ? old.filter(d => d.id !== deal.id) : [deal, ...old].slice(0, 100); try { localStorage.setItem('promodev-saved-v1', JSON.stringify(next)); } catch {} return next; });
  }
  return <SavedContext.Provider value={{ saved, toggle }}>{children}</SavedContext.Provider>;
}
export const useSaved = () => useContext(SavedContext);
export function PageHeading({ title, text }: { title: string; text?: string }) {
  return <header className="page-heading"><h1>{title}</h1>{text && <p>{text}</p>}</header>;
}
export function Breadcrumb({ items }: { items: [string, string?][] }) {
  return <nav className="breadcrumb" aria-label="Trilha"><Link to="/">Início</Link>{items.map(([label, to]) => <span key={label}><i aria-hidden="true">/</i>{to ? <Link to={to}>{label}</Link> : <span aria-current="page">{label}</span>}</span>)}</nav>;
}
export function Empty({ title = 'Nenhuma oferta por aqui ainda', text = 'Experimente outra categoria ou volte em breve.' }: { title?: string; text?: string }) {
  return <div className="empty-state"><span className="empty-icon"><Icon name="search" size={28}/></span><h2>{title}</h2><p>{text}</p><Link className="button secondary" to="/ofertas">Ver ofertas<Icon name="arrow" size={16}/></Link></div>;
}
export function Failure({ error, retry }: { error: string; retry: () => void }) { return <div className="error-state" role="alert"><p>{error}</p><button className="button secondary" onClick={retry}>Tentar novamente</button></div>; }
export function Loading({ count = 4 }: { count?: number }) { return <div className="deal-grid" role="status" aria-label="Carregando ofertas">{Array.from({ length: count }, (_, n) => <div className="skeleton-card" key={n}><div/><span/><span/><span/></div>)}</div>; }
export function SectionHeading({ title, text, to, link = 'Ver todas' }: { title: string; text?: string; to?: string; link?: string }) {
  return <div className="section-heading"><div><h2>{title}</h2>{text && <p>{text}</p>}</div>{to && <Link className="text-link" to={to}>{link}<Icon name="arrow" size={16}/></Link>}</div>;
}
export function Pagination({ page, total, pageSize, onPage }: { page: number; total: number; pageSize: number; onPage: (page: number) => void }) {
  const count = Math.ceil(total / pageSize); if (count <= 1) return null;
  const start = Math.max(1, Math.min(page - 2, count - 4)); const pages = Array.from({ length: Math.min(5, count) }, (_, i) => start + i);
  return <nav className="pagination" aria-label="Paginação"><button disabled={page <= 1} aria-label="Página anterior" onClick={() => onPage(page - 1)}><Icon name="back" size={16}/></button>
    {pages.map(n => <button key={n} className={n === page ? 'current' : ''} aria-current={n === page ? 'page' : undefined} onClick={() => onPage(n)}>{n}</button>)}
    <button disabled={page >= count} aria-label="Próxima página" onClick={() => onPage(page + 1)}><Icon name="chevron" size={16}/></button></nav>;
}
export function CouponCode({ code }: { code: string }) {
  const [state, setState] = useState('');
  async function copy() { try { await navigator.clipboard.writeText(code); setState('Copiado'); } catch { setState('Selecione o código'); } }
  return <div className="coupon-copy"><code>{code}</code><button onClick={copy} aria-label={`Copiar cupom ${code}`}><Icon name={state === 'Copiado' ? 'check' : 'copy'} size={14}/>{state || 'Copiar'}</button><span className="sr-only" role="status">{state}</span></div>;
}
export async function share(title: string, path: string) {
  const url = new URL(path, window.location.origin).href;
  if (navigator.share) { try { await navigator.share({ title, url }); return 'Compartilhado'; } catch (error) { if ((error as Error).name === 'AbortError') return ''; } }
  try { await navigator.clipboard.writeText(url); return 'Link copiado'; } catch { return 'Não foi possível copiar'; }
}
