import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { CATEGORIES, CATEGORY_LINKS, PRICE_LINKS, STORE_OPTIONS } from './api';
import { Icon } from './ui';

// Menu de categorias no estilo mega-menu: lista à esquerda, atalhos da categoria ativa à direita.
// Abre ao passar o mouse ou ao clicar; no celular o botão abre a folha (onMobile).
export default function CategoryMenu({ onMobile }: { onMobile: () => void }) {
  const [open, setOpen] = useState(false); const [active, setActive] = useState(CATEGORIES[0].id);
  const root = useRef<HTMLDivElement>(null); const closeTimer = useRef<number>(); const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname, location.search]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(false); root.current?.querySelector('button')?.focus(); } };
    const onClick = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('keydown', onKey); document.addEventListener('mousedown', onClick);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onClick); };
  }, [open]);
  const mobile = () => window.matchMedia('(max-width: 760px)').matches;
  function hover(next: boolean) { if (mobile()) return; window.clearTimeout(closeTimer.current); if (next) setOpen(true); else closeTimer.current = window.setTimeout(() => setOpen(false), 150); }
  const category = CATEGORIES.find(c => c.id === active) || CATEGORIES[0]; const base = `/categoria/${category.id}`;
  return <div className="category-menu" ref={root} onMouseEnter={() => hover(true)} onMouseLeave={() => hover(false)}>
    <button className="categories-button" aria-expanded={open} aria-controls="category-panel" onClick={() => mobile() ? onMobile() : setOpen(v => !v)}>
      <Icon name="grid" size={16}/>Categorias<Icon name="chevron" size={14} className="caret"/></button>
    {open && <div className="mega-menu" id="category-panel"><div className="container mega-inner">
      <ul className="mega-list">{CATEGORIES.map(c => <li key={c.id}><Link to={`/categoria/${c.id}`} className={c.id === active ? 'active' : ''} onMouseEnter={() => setActive(c.id)} onFocus={() => setActive(c.id)}>
        <Icon name={c.icon} size={18}/>{c.label}<Icon name="chevron" size={14}/></Link></li>)}
        <li className="mega-all"><Link to="/categorias">Todas as categorias</Link></li></ul>
      <div className="mega-panel">
        <div className="mega-title"><h2>{category.label}</h2><Link className="text-link" to={base}>Ver todas as ofertas<Icon name="arrow" size={16}/></Link></div>
        <div className="mega-columns">
          <div><h3>Produtos</h3>{(CATEGORY_LINKS[category.id] || []).map(([label, q]) => <Link key={q} to={`${base}?q=${encodeURIComponent(q)}`}>{label}</Link>)}</div>
          <div><h3>Por loja</h3>{STORE_OPTIONS.map(s => <Link key={s.id} to={`${base}?store=${s.id}`}><i className={`store-dot ${s.id}`}/>{s.label}</Link>)}</div>
          <div><h3>Preço e desconto</h3>{PRICE_LINKS.map(([label, query]) => <Link key={query} to={`${base}?${query}`}>{label}</Link>)}
            <Link to={`${base}?sort=best_selling`}>Mais vendidos</Link></div>
        </div>
      </div>
    </div></div>}
  </div>;
}
