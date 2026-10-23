import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Layout from './Layout';
import { Empty, SavedProvider } from './ui';
const Home = lazy(() => import('./Home'));
const Catalog = lazy(() => import('./Catalog'));
const Favorites = lazy(() => import('./Catalog').then(m => ({ default: m.Favorites })));
const Directory = lazy(() => import('./Catalog').then(m => ({ default: m.Directory })));
const Promotions = lazy(() => import('./Promotions'));
const CampaignDetail = lazy(() => import('./Promotions').then(m => ({ default: m.CampaignDetail })));
const DealPage = lazy(() => import('./DealPage'));
const Legal = lazy(() => import('./Legal'));
export default function App() {
  return <BrowserRouter><SavedProvider><Suspense fallback={<div className="container page-space loading-line" role="status">Carregando…</div>}><Routes><Route element={<Layout/>}>
    <Route path="/" element={<Home/>}/><Route path="/ofertas" element={<Catalog/>}/><Route path="/maiores-descontos" element={<Catalog/>}/><Route path="/busca" element={<Catalog/>}/>
    <Route path="/categoria/:category" element={<Catalog/>}/><Route path="/categorias" element={<Directory kind="categories"/>}/><Route path="/loja/:store" element={<Catalog/>}/><Route path="/lojas" element={<Directory kind="stores"/>}/>
    <Route path="/campanhas" element={<Promotions kind="campaign"/>}/><Route path="/cupons" element={<Promotions kind="coupon"/>}/><Route path="/campanha/:slug" element={<CampaignDetail/>}/>
    <Route path="/oferta/:slug" element={<DealPage/>}/><Route path="/favoritos" element={<Favorites/>}/><Route path="/privacidade" element={<Legal kind="privacidade"/>}/><Route path="/termos" element={<Legal kind="termos"/>}/>
    <Route path="*" element={<div className="container page-space"><Empty title="Página não encontrada"/></div>}/>
  </Route></Routes></Suspense></SavedProvider></BrowserRouter>;
}
