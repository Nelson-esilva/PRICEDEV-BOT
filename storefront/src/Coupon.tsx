import { useState } from "react";
import Icon from "./Icon";

export default function Coupon({ code }: { code: string }) {
  const [status, setStatus] = useState("");
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setStatus("Cupom copiado!");
    } catch {
      setStatus(`Copie o código: ${code}`);
    }
  }
  return (
    <div className="coupon-wrap">
      <button
        className="coupon"
        onClick={copy}
        aria-label={`Copiar cupom ${code}`}
      >
        <Icon name="tag" size={15} />
        <span>
          Cupom <b>{code}</b>
        </span>
        <Icon name={status === "Cupom copiado!" ? "check" : "copy"} size={15} />
      </button>
      <span className="coupon-status" role="status">
        {status}
      </span>
    </div>
  );
}
