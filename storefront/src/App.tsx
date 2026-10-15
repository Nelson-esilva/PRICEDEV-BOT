import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Catalog from "./Catalog";
import DealPage from "./DealPage";
import Layout from "./Layout";
import Legal from "./Legal";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Catalog />} />
          <Route path="/loja/:store" element={<Catalog />} />
          <Route path="/categoria/:category" element={<Catalog />} />
          <Route path="/busca" element={<Catalog />} />
          <Route path="/oferta/:slug" element={<DealPage />} />
          <Route path="/privacidade" element={<Legal kind="privacidade" />} />
          <Route path="/termos" element={<Legal kind="termos" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
