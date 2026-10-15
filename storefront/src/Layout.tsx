import { FormEvent, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useSearchParams } from "react-router-dom";

export default function Layout() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");

  function onSearch(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    navigate(q ? `/busca?q=${encodeURIComponent(q)}` : "/");
  }

  return (
    <div className="shell">
      <header className="top">
        <Link className="brand" to="/">
          PromoDev
        </Link>
        <form className="search-box" onSubmit={onSearch}>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar ofertas"
            aria-label="Buscar ofertas"
          />
          <button type="submit">Buscar</button>
        </form>
        <nav className="top-nav">
          <NavLink to="/" end>
            Ofertas
          </NavLink>
          <NavLink to="/loja/shopee">Shopee</NavLink>
          <NavLink to="/loja/mercadolivre">Mercado Livre</NavLink>
        </nav>
      </header>
      <Outlet />
      <footer className="site-foot">
        <p>
          Alguns links são de afiliados. Podemos receber comissão se você comprar, sem custo extra para você.
          O preço e a disponibilidade são da loja e podem mudar no checkout.
        </p>
        <nav>
          <Link to="/privacidade">Privacidade</Link>
          <Link to="/termos">Termos</Link>
        </nav>
      </footer>
      <nav className="bottom-nav" aria-label="Navegação móvel">
        <NavLink to="/" end>
          Ofertas
        </NavLink>
        <NavLink to="/loja/shopee">Shopee</NavLink>
        <NavLink to="/loja/mercadolivre">ML</NavLink>
      </nav>
    </div>
  );
}
