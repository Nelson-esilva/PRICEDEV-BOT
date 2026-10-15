import { Link } from "react-router-dom";

export default function Legal({ kind }: { kind: "privacidade" | "termos" }) {
  if (kind === "privacidade") {
    return (
      <main className="legal">
        <h1>Privacidade</h1>
        <p>
          A vitrine pública não cria conta e não guarda mensagens de grupos. Quando você clica em
          comprar, registramos só o horário, a oferta e o navegador, para medir o clique do afiliado.
        </p>
        <p>Não vendemos esses dados. Dúvidas: use o canal PromoDev.</p>
        <Link to="/">Voltar</Link>
      </main>
    );
  }
  return (
    <main className="legal">
      <h1>Termos e divulgação</h1>
      <p>
        O PromoDev é um site de divulgação de ofertas. Alguns links são de programas de afiliados
        (Shopee, Mercado Livre e outros). Se você comprar por eles, podemos receber comissão, sem
        custo extra para você.
      </p>
      <p>
        Não vendemos os produtos. Preço, estoque, frete e garantia são da loja. Confira tudo no
        checkout antes de pagar.
      </p>
      <Link to="/">Voltar</Link>
    </main>
  );
}
