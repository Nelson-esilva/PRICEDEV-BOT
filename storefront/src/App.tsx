import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Layout from './Layout';
import { Empty, Loading, SavedProvider } from './ui';

// Enquanto o código da página chega: barra de progresso no topo + esqueleto dos cartões.
function PageLoading() {
  return <><div className="route-progress" aria-hidden="true"/><div className="container page-space"><Loading count={8}/></div></>;
}
const Home = lazy(() => import('./Home'));
const Catalog = lazy(() => import('./Catalog'));
const Favorites = lazy(() => import('./Catalog').then(m => ({ default: m.Favorites })));
const Directory = lazy(() => import('./Catalog').then(m => ({ default: m.Directory })));
const Promotions = lazy(() => import('./Promotions'));
const CampaignDetail = lazy(() => import('./Promotions').then(m => ({ default: m.CampaignDetail })));
const DealPage = lazy(() => import('./DealPage'));
const Legal = lazy(() => import('./Legal'));
const RankingIndex = lazy(() => import('./Rankings').then(m => ({ default: m.RankingIndex })));
const RankingPage = lazy(() => import('./Rankings').then(m => ({ default: m.RankingPage })));
// Baixa em segundo plano o código das páginas mais visitadas: o primeiro clique não espera.
const PRELOAD = () => { import('./DealPage'); import('./Catalog'); import('./Promotions'); import('./Rankings'); };
if (typeof window !== 'undefined') window.addEventListener('load', () => setTimeout(PRELOAD, 800), { once: true });

export default function App() {
  return <BrowserRouter><SavedProvider><Suspense fallback={<PageLoading/>}><Routes><Route element={<Layout/>}>
    <Route path="/" element={<Home/>}/><Route path="/ofertas" element={<Catalog/>}/><Route path="/maiores-descontos" element={<Catalog/>}/><Route path="/busca" element={<Catalog/>}/><Route path="/em-alta" element={<Catalog/>}/>
    <Route path="/rankings" element={<RankingIndex/>}/><Route path="/ranking/:id" element={<RankingPage/>}/>
    <Route path="/categoria/:category" element={<Catalog/>}/><Route path="/categorias" element={<Directory kind="categories"/>}/><Route path="/loja/:store" element={<Catalog/>}/><Route path="/lojas" element={<Directory kind="stores"/>}/>
    <Route path="/campanhas" element={<Promotions kind="campaign"/>}/><Route path="/cupons" element={<Promotions kind="coupon"/>}/><Route path="/campanha/:slug" element={<CampaignDetail/>}/>
    <Route path="/oferta/:slug" element={<DealPage/>}/><Route path="/favoritos" element={<Favorites/>}/><Route path="/privacidade" element={<Legal kind="privacidade"/>}/><Route path="/termos" element={<Legal kind="termos"/>}/>
    <Route path="*" element={<div className="container page-space"><Empty title="Página não encontrada"/></div>}/>
  </Route></Routes></Suspense></SavedProvider></BrowserRouter>;
}
