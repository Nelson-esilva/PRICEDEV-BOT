import { useState } from "react";
import Icon from "./Icon";

export default function ProductImage({
  src,
  name,
  eager = false,
}: {
  src: string | null;
  name: string;
  eager?: boolean;
}) {
  const [failedSource, setFailedSource] = useState<string | null>(null);
  if (!src || failedSource === src)
    return (
      <div
        className="image-placeholder"
        role="img"
        aria-label={`${name}: imagem indisponível`}
      >
        <Icon name="bag" size={40} />
        <span>Imagem indisponível</span>
      </div>
    );
  return (
    <img
      src={src}
      alt={name}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      onError={() => setFailedSource(src)}
    />
  );
}
