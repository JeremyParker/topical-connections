import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Topic } from "../api";
import { MAX_WORD_LENGTH, studio, type WordDetail } from "./api";
import CategoryForm from "./CategoryForm";
import { useAction, useDebounced, useLoad } from "./hooks";
import LinkEditor from "./LinkEditor";

export default function WordPage({ id, topic }: { id: number; topic: Topic }) {
  const { data, error, reload } = useLoad(() => studio.word(id), [id]);
  if (!data) return error ? <p role="alert">{error}</p> : <p>Loading…</p>;
  return (
    <>
      <h1>{data.text}</h1>
      {error && <p role="alert">{error}</p>}
      <p>{data.is_topical ? "Topical" : "Not topical"}, based on its categories.</p>
      <table>
        <thead>
          <tr>
            <th>Category</th>
            <th>Difficulty</th>
            <th>Example sentence</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.categories.map((c) => (
            <tr key={c.link_id}>
              <td>
                <Link to={`/studio/categories/${c.category_id}`}>{c.name}</Link>
                {c.is_topical && " (topical)"}
              </td>
              <LinkEditor
                linkId={c.link_id}
                name={c.name}
                fields={c}
                inherited={c.difficulty}
                onChange={reload}
              />
            </tr>
          ))}
        </tbody>
      </table>
      <AddMeaning word={data} topic={topic} onAdded={reload} />
      <EditWord word={data} onSaved={reload} />
    </>
  );
}

type AddMeaningProps = { word: WordDetail; topic: Topic; onAdded: () => Promise<unknown> };

function AddMeaning({ word, topic, onAdded }: AddMeaningProps) {
  const [typed, setTyped] = useState("");
  const [creating, setCreating] = useState(false);
  const search = useDebounced(typed.trim());
  const { data } = useLoad(
    async () => (search ? (await studio.categories({ search })).items : []),
    [search],
  );
  const { busy, error, run } = useAction();

  const used = new Set(word.categories.map((c) => c.category_id));
  const matches = typed.trim() ? (data ?? []).filter((c) => !used.has(c.id)).slice(0, 8) : [];

  async function add(categoryId: number) {
    await studio.createLink(word.id, categoryId);
    setTyped("");
    setCreating(false);
    await onAdded();
  }

  return (
    <section>
      <h2>Add another meaning</h2>
      <label>
        Find a category
        <input type="search" value={typed} onChange={(e) => setTyped(e.target.value)} />
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="row">
        {matches.map((c) => (
          <button key={c.id} disabled={busy} onClick={() => run(() => add(c.id))}>
            {c.name} ({c.word_count})
          </button>
        ))}
        {typed.trim() && !creating && (
          <button onClick={() => setCreating(true)}>New category “{typed.trim()}”</button>
        )}
      </div>
      {creating && (
        <CategoryForm
          topic={topic}
          initial={{ name: typed.trim(), notes: null, difficulty: 1, is_topical: false }}
          submitLabel={`Create category and add ${word.text}`}
          onSubmit={async (fields) => add((await studio.createCategory(fields)).id)}
        />
      )}
    </section>
  );
}

function EditWord({ word, onSaved }: { word: WordDetail; onSaved: () => Promise<unknown> }) {
  const navigate = useNavigate();
  const [text, setText] = useState(word.text);
  const { busy, error, run } = useAction();

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      await studio.updateWord(word.id, text);
      await onSaved();
    });
  }

  function confirmDelete() {
    if (!window.confirm(`Delete “${word.text}” from every category?`)) return;
    void run(async () => {
      await studio.deleteWord(word.id);
      navigate("/studio/words");
    });
  }

  return (
    <details>
      <summary>Edit word</summary>
      <form onSubmit={submit}>
        <label>
          Word or phrase
          <input
            required
            maxLength={MAX_WORD_LENGTH}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <div className="row">
          <button disabled={busy}>Save word</button>
          <button type="button" disabled={busy} onClick={confirmDelete}>
            Delete word
          </button>
        </div>
      </form>
    </details>
  );
}
