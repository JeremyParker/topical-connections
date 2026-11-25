import { type FormEvent, useRef, useState } from "react";
import { type BulkResult, MAX_BULK_WORDS, studio } from "./api";
import { useAction, useDebounced, useLoad } from "./hooks";

/** One word per line, or commas if it's all on one line. */
export function splitWords(text: string): string[] {
  const separator = text.trim().includes("\n") ? "\n" : /[,\n]/;
  return text
    .split(separator)
    .map((word) => word.trim())
    .filter(Boolean);
}

type Props = { categoryId: number; existing: string[]; onAdded: () => Promise<unknown> };

export default function AddWords({ categoryId, existing, onAdded }: Props) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<BulkResult | null>(null);
  const { busy, error, run } = useAction();
  const box = useRef<HTMLTextAreaElement>(null);

  const words = splitWords(text);
  const lastLine = text.slice(text.lastIndexOf("\n") + 1);
  // Suggests existing words for the line being typed, to avoid near-duplicates.
  const partial = useDebounced(lastLine.includes(",") ? "" : lastLine.trim());
  const { data: suggestions } = useLoad(
    async () => (partial.length < 2 ? [] : (await studio.words({ search: partial })).items),
    [partial],
  );
  const inCategory = new Set(existing.map((word) => word.toLowerCase()));
  const offered = (lastLine.trim() ? (suggestions ?? []) : [])
    .filter((w) => !inCategory.has(w.text.toLowerCase()))
    .slice(0, 6);

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      setResult(null);
      setResult(await studio.addWords(categoryId, words));
      setText("");
      await onAdded();
      box.current?.focus();
    });
  }

  function accept(word: string) {
    setText(`${text.slice(0, text.length - lastLine.length)}${word}\n`);
    box.current?.focus();
  }

  return (
    <form onSubmit={submit}>
      <label>
        Add words, one per line
        <textarea
          ref={box}
          rows={5}
          value={text}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
          }}
        />
      </label>
      {offered.length > 0 && (
        <div className="row">
          Existing words:
          {offered.map((w) => (
            <button type="button" key={w.id} onClick={() => accept(w.text)}>
              {w.text}
            </button>
          ))}
        </div>
      )}
      {error && <p role="alert">{error}</p>}
      {words.length > MAX_BULK_WORDS && (
        <p role="alert">Please add at most {MAX_BULK_WORDS} words at a time.</p>
      )}
      <button disabled={busy || words.length === 0 || words.length > MAX_BULK_WORDS}>
        Add {words.length || ""} {words.length === 1 ? "word" : "words"}
      </button>
      <div role="status">
        {result && (
          <ul>
            <Outcome label="New words" words={result.created} />
            <Outcome label="Existing words added" words={result.linked} />
            <Outcome label="Already in this category" words={result.already_there} />
            <Outcome label="Not added (too long or invalid)" words={result.invalid} />
          </ul>
        )}
      </div>
    </form>
  );
}

function Outcome({ label, words }: { label: string; words: string[] }) {
  if (words.length === 0) return null;
  return (
    <li>
      {label}: {words.join(", ")}
    </li>
  );
}
