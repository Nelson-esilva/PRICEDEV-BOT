import { createContext, useContext, useEffect, useRef, useState, type FormEvent } from 'react';
import { flushSync } from 'react-dom';
import { Link, NavLink, Outlet, useLocation, useNavigate, useNavigationType, useSearchParams } from 'react-router-dom';
import { CATEGORIES, type SiteInfo } from './api';
import { Brand, Icon, useRemote, useSaved } from './ui';

const positions = new Map<string, number>();
function ScrollManager() {
  const location = useLocation(); const nav = useNavigationType();
  useEffect(() => {
    const frame = requestAnimationFrame(() => window.scrollTo(0, nav === 'POP' ? positions.get(location.key) || 0 : 0));
    return () => { cancelAnimationFrame(frame); positions.set(location.key, window.scrollY); };
  }, [location.key, nav]);
  return null;
}

// Transição entre páginas: nos navegadores com View Transitions, a página antiga se dissolve
// na nova (cabeçalho parado, volta ao topo dentro da transição). Os demais seguem com o
// esmaecer de entrada (.page-enter). Escuta na captura, antes do onClick dos <Link>.
type ViewTransitionDocument = Document & { startViewTransition?: (update: () => void) => unknown };
function useViewTransitions() {
  const navigate = useNavigate();
  useEffect(() => {
    const doc = document as ViewTransitionDocument;
    if (!doc.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    function onClick(event: MouseEvent) {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null;
      if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download') || anchor.origin !== location.origin) return;
      const path = anchor.pathname + anchor.search + anchor.hash;
      if (/^\/(go|api)\//.test(anchor.pathname) || anchor.hash && anchor.pathname === location.pathname) return;
      event.preventDefault();
      if (path === location.pathname + location.search + location.hash) return;
      doc.startViewTransition!(() => { flushSync(() => navigate(path)); window.scrollTo(0, 0); });
    }
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [navigate]);
}

// Link do grupo e contagem por loja, usados no topo, no menu lateral e nas chamadas do Telegram.
const SiteContext = createContext<SiteInfo | null>(null);
export function useSite() { return useContext(SiteContext); }

const SHORTCUTS: [string, string][] = [['/ofertas', 'Ofertas do dia'], ['/rankings', 'Rankings'], ['/cupons', 'Cupons'],
  ['/ofertas?pix=true', 'Ofertas no Pix'], ['/ofertas?free_shipping=true', 'Frete grátis'], ['/categoria/informatica', 'Informática'], ['/categoria/casa', 'Casa & cozinha']];

export default function Layout() {
  const navigate = useNavigate(); const [params] = useSearchParams(); const location = useLocation();
  const [query, setQuery] = useState(params.get('q') || ''); const { saved } = useSaved(); const drawer = useRef<HTMLDialogElement>(null);
  const site = useRemote<SiteInfo>('/site').data || null;
  useViewTransitions();
  useEffect(() => { setQuery(params.get('q') || ''); }, [location.search]);
  useEffect(() => { drawer.current?.close(); }, [location.pathname, location.search]);
  function search(e: FormEvent) { e.preventDefault(); navigate(`/busca${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ''}`); }
  const open = () => drawer.current?.showModal();
  return <SiteContext.Provider value={site}><ScrollManager/><a className="skip-link" href="#main">Pular para o conteúdo</a>
    <header className="site-header">
      <div className="wide header-main">
        <button className="icon-button menu-trigger mobile-only" aria-label="Abrir menu" onClick={open}><Icon name="menu"/></button>
        <Link className="brand" to="/" aria-label="PromoDev, início"><Brand/></Link>
        <form className="global-search" onSubmit={search} role="search"><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Buscar produtos, lojas ou cupons" aria-label="Buscar produtos e ofertas"/><button type="submit" aria-label="Buscar"><Icon name="search" size={22}/></button></form>
        {site?.telegram_url && <a className="header-telegram" href={site.telegram_url} target="_blank" rel="noopener"><span>Receba ofertas</span><strong>Grupo no Telegram</strong></a>}
        <Link className="header-saved" to="/favoritos" aria-label={`Favoritos${saved.length ? `, ${saved.length} salvos` : ''}`}><Icon name="heart"/><span>Favoritos</span>{saved.length > 0 && <span className="count">{saved.length}</span>}</Link>
      </div>
      <nav className="shortcut-bar" aria-label="Atalhos"><div className="wide shortcut-inner">
        <button className="all-button" onClick={open}><Icon name="menu" size={20}/>Todos</button>
        <NavLink to="/em-alta" className="hot-link"><Icon name="flame" size={16}/>Em alta agora</NavLink>
        {SHORTCUTS.map(([to, label]) => <Link key={to} to={to}>{label}</Link>)}
        <span className="shortcut-note">Ofertas novas a cada hora</span>
      </div></nav>
    </header>
    <dialog ref={drawer} className="drawer" aria-label="Menu principal" onClick={e => { if (e.target === drawer.current) drawer.current?.close(); }}>
      <div className="drawer-panel">
        <div className="drawer-top"><span className="drawer-mark"><Brand size={24}/></span><span><strong>Olá! Bora economizar?</strong><span>Ofertas de {site?.stores.length || 4} lojas em um só lugar</span></span></div>
        <div className="drawer-body">
          <DrawerSection title="Destaques" items={[['/em-alta', 'Em alta agora', 'novo'], ['/ofertas', 'Ofertas do dia'], ['/rankings', 'Rankings de mais vendidos'], ['/maiores-descontos', 'Maiores descontos']]}/>
          <DrawerSection title="Comprar por loja" items={(site?.stores || []).map(s => [`/loja/${s.id}`, s.label, s.count ? `${s.count} ofertas` : undefined] as [string, string, string?])} info/>
          <DrawerSection title="Comprar por categoria" items={[...CATEGORIES.slice(0, 6).map(c => [`/categoria/${c.id}`, c.label] as [string, string]), ['/categorias', 'Ver todas as categorias']]}/>
          <DrawerSection title="Cupons e economia" items={[['/cupons', 'Cupons do dia'], ['/ofertas?pix=true', 'Ofertas no Pix'], ['/ofertas?free_shipping=true', 'Frete grátis'], ['/ofertas?max_price=50', 'Achados até R$ 50'], ['/campanhas', 'Campanhas das lojas']]}/>
          <DrawerSection title="Sua conta" items={[['/favoritos', 'Favoritos'], ['/termos', 'Como escolhemos as ofertas'], ['/privacidade', 'Privacidade e termos']]}/>
          {site?.telegram_url && <div className="drawer-telegram"><strong>Ofertas no seu celular</strong><span>Entre no grupo do Telegram e receba promoções e cupons assim que aparecem.</span><a href={site.telegram_url} target="_blank" rel="noopener">Entrar no grupo</a></div>}
        </div>
      </div>
      <button className="drawer-close" aria-label="Fechar menu" onClick={() => drawer.current?.close()}><Icon name="close"/></button>
    </dialog>
    {/* A chave por rota remonta o conteúdo e dispara a animação de entrada a cada troca de página. */}
    <main id="main" tabIndex={-1}><div key={location.pathname} className="page-enter"><Outlet/></div></main>
    <footer className="site-footer">
      <button className="back-top" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>Voltar ao início</button>
      <div className="footer-grid">
        <div><h3>Explorar</h3><Link to="/em-alta">Em alta agora</Link><Link to="/rankings">Rankings de mais vendidos</Link><Link to="/maiores-descontos">Maiores descontos</Link><Link to="/ofertas?pix=true">Ofertas no Pix</Link></div>
        <div><h3>Lojas</h3>{(site?.stores || []).map(s => <Link key={s.id} to={`/loja/${s.id}`}>{s.label}</Link>)}</div>
        <div><h3>Cupons e campanhas</h3><Link to="/cupons">Cupons do dia</Link><Link to="/campanhas">Campanhas das lojas</Link><Link to="/ofertas?free_shipping=true">Frete grátis</Link>{site?.telegram_url && <a href={site.telegram_url} target="_blank" rel="noopener">Grupo no Telegram</a>}</div>
        <div><h3>PromoDev</h3><Link to="/termos">Como escolhemos as ofertas</Link><Link to="/favoritos">Favoritos</Link><Link to="/privacidade">Privacidade</Link><Link to="/termos">Termos de uso</Link></div>
      </div>
      <div className="footer-bottom"><Brand size={28}/><span>Podemos receber comissão pelas compras feitas pelos nossos links, sem custo extra para você. Preços e disponibilidade podem mudar; confira na loja.</span><span>© {new Date().getFullYear()} PromoDev</span></div>
    </footer>
  </SiteContext.Provider>;
}

function DrawerSection({ title, items, info = false }: { title: string; items: [string, string, string?][]; info?: boolean }) {
  if (!items.length) return null;
  return <section className="drawer-section"><h2>{title}</h2><ul>{items.map(([to, label, badge]) => <li key={to + label}>
    <Link to={to}><span>{label}</span>{badge && <span className={`drawer-badge ${info ? 'info' : 'hot'}`}>{badge}</span>}<Icon name="chevron" size={16}/></Link></li>)}</ul></section>;
}
