import { type ReactNode, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useDebounced } from "./hooks";

const PAGE_SIZE = 50;

/** Search, filter and page, kept in the URL so that Back returns to them. */
export function useListParams() {
  const [params, setParams] = useSearchParams();
  const search = params.get("search") ?? "";
  const only = params.get("only") ?? "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);

  function update(changes: { search?: string; only?: string; offset?: number }) {
    setParams(
      (old) => {
        const next = new URLSearchParams(old);
        next.delete("offset"); // a new search starts from the first page
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, String(value));
          else next.delete(key);
        }
        return next;
      },
      { replace: changes.offset === undefined },
    );
  }
  return { search, only, offset, update };
}

type Props = ReturnType<typeof useListParams> & {
  label: string;
  filters: Record<string, string>;
  total: number | undefined;
  children: ReactNode;
};

export default function ListControls(props: Props) {
  const { search, only, offset, update, label, filters, total, children } = props;
  const [typed, setTyped] = useState(search);
  const settled = useDebounced(typed);

  useEffect(() => {
    if (settled !== search) update({ search: settled });
    // Only when typing settles. Navigation may change the URL's search too.
  }, [settled]);
  useEffect(() => setTyped(search), [search]);

  return (
    <>
      <div className="row">
        <label className="grow">
          {label}
          <input type="search" value={typed} onChange={(e) => setTyped(e.target.value)} />
        </label>
        <label>
          Show
          <select value={only} onChange={(e) => update({ only: e.target.value })}>
            <option value="">All</option>
            {Object.entries(filters).map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </label>
      </div>
      {children}
      {total !== undefined && (
        <div className="row">
          <span className="grow">
            {total === 0
              ? "Nothing found."
              : `${Math.min(offset + 1, total)}–${Math.min(offset + PAGE_SIZE, total)} of ${total}`}
          </span>
          <button
            disabled={offset === 0}
            onClick={() => update({ offset: Math.max(0, offset - PAGE_SIZE) })}
          >
            Previous
          </button>
          <button
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => update({ offset: offset + PAGE_SIZE })}
          >
            Next
          </button>
        </div>
      )}
    </>
  );
}
