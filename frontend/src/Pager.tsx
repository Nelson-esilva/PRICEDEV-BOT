type PagerProps = {
  page: number;
  pageCount: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
};

function pageWindow(page: number, pageCount: number, size = 10): number[] {
  if (pageCount <= size) {
    return Array.from({ length: pageCount }, (_, i) => i + 1);
  }
  const half = Math.floor(size / 2);
  let start = Math.max(1, page - half);
  let end = start + size - 1;
  if (end > pageCount) {
    end = pageCount;
    start = Math.max(1, end - size + 1);
  }
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}

export default function Pager({ page, pageCount, total, pageSize, onPage }: PagerProps) {
  if (total <= pageSize) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return (
    <div className="pager">
      <span>
        {from} a {to} de {total} registros
      </span>
      <div className="pager-nums">
        <button type="button" disabled={page <= 1} aria-label="Primeira página" onClick={() => onPage(1)}>
          {"<<"}
        </button>
        <button type="button" disabled={page <= 1} aria-label="Página anterior" onClick={() => onPage(page - 1)}>
          {"<"}
        </button>
        {pageWindow(page, pageCount).map((n) => (
          <button
            key={n}
            type="button"
            className={n === page ? "on" : undefined}
            onClick={() => onPage(n)}
          >
            {n}
          </button>
        ))}
        <button
          type="button"
          disabled={page >= pageCount}
          aria-label="Próxima página"
          onClick={() => onPage(page + 1)}
        >
          {">"}
        </button>
        <button
          type="button"
          disabled={page >= pageCount}
          aria-label="Última página"
          onClick={() => onPage(pageCount)}
        >
          {">>"}
        </button>
      </div>
    </div>
  );
}
