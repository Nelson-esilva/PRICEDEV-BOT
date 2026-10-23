import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate, useNavigationType, useSearchParams } from 'react-router-dom';
import { CATEGORIES } from './api';
import { Brand, Icon, useSaved } from './ui';

const positions = new Map<string, number>();
function ScrollManager() {
  const location = useLocation(); const nav = useNavigationType();
  useEffect(() => {
    const frame = requestAnimationFrame(() => window.scrollTo(0, nav === 'POP' ? positions.get(location.key) || 0 : 0));
    return () => { cancelAnimationFrame(frame); positions.set(location.key, window.scrollY); };
  }, [location.key, nav]);
  return null;
}
export default function Layout() {
  const navigate = useNavigate(); const [params] = useSearchParams(); const location = useLocation();
  const [query, setQuery] = useState(params.get('q') || ''); const { saved } = useSaved(); const menu = useRef<HTMLDialogElement>(null);
  useEffect(() => { setQuery(params.get('q') || ''); }, [location.search]);
  function search(e: FormEvent) { e.preventDefault(); navigate(`/busca${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ''}`); }
  const links = [['/ofertas', 'Ofertas'], ['/maiores-descontos', 'Maiores descontos'], ['/campanhas', 'Campanhas'], ['/cupons', 'Cupons'], ['/lojas', 'Lojas']];
  return <><ScrollManager/><a className="skip-link" href="#main">Pular para o conteúdo</a>
    <header className="site-header"><div className="container header-main">
      <Link className="brand" to="/" aria-label="PromoDev, início"><Brand/></Link>
      <form className="global-search" onSubmit={search} role="search"><Icon name="search" size={18}/><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Buscar produtos, lojas ou cupons" aria-label="Buscar produtos e ofertas"/><button type="submit">Buscar</button></form>
      <Link className="header-saved" to="/favoritos"><Icon name="heart"/>Favoritos{saved.length > 0 && <span className="count" aria-label={`${saved.length} salvos`}>{saved.length}</span>}</Link>
    </div><nav className="container desktop-nav" aria-label="Principal"><button className="categories-button" onClick={() => menu.current?.showModal()}><Icon name="grid" size={16}/>Categorias</button>{links.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}</nav></header>
    <dialog ref={menu} className="sheet"><div className="sheet-top"><h2>Categorias</h2><button className="icon-button" aria-label="Fechar categorias" onClick={() => menu.current?.close()}><Icon name="close"/></button></div><div className="category-list">{CATEGORIES.map(c => <Link to={`/categoria/${c.id}`} key={c.id} onClick={() => menu.current?.close()}><Icon name={c.icon}/>{c.label}<Icon name="chevron" size={16}/></Link>)}</div></dialog>
    <main id="main" tabIndex={-1}><Outlet/></main>
    <footer className="site-footer"><div className="container footer-grid"><div className="footer-brand"><Brand size={28}/><p>Podemos receber comissão pelas compras feitas pelos nossos links, sem custo extra para você. Preços e disponibilidade podem mudar; confira na loja.</p></div>
      <div><h3>Explorar</h3><Link to="/ofertas">Ofertas</Link><Link to="/maiores-descontos">Maiores descontos</Link><Link to="/campanhas">Campanhas</Link><Link to="/cupons">Cupons</Link></div>
      <div><h3>PromoDev</h3><Link to="/categorias">Categorias</Link><Link to="/lojas">Lojas</Link><Link to="/favoritos">Favoritos</Link><Link to="/privacidade">Privacidade</Link><Link to="/termos">Termos de uso</Link></div></div>
      <div className="container footer-bottom">© {new Date().getFullYear()} PromoDev</div></footer>
    <nav className="mobile-nav" aria-label="Navegação móvel">{[['/', 'home', 'Início'], ['/categorias', 'grid', 'Explorar'], ['/cupons', 'ticket', 'Cupons'], ['/favoritos', 'heart', 'Favoritos']].map(([to, icon, label]) => <NavLink key={to} to={to} end={to === '/'}><Icon name={icon} size={22}/><span>{label}</span></NavLink>)}</nav>
  </>;
}
