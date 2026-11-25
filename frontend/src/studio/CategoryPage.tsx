import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Topic } from "../api";
import AddWords from "./AddWords";
import { studio } from "./api";
import CategoryForm from "./CategoryForm";
import { useAction, useLoad } from "./hooks";
import LinkEditor from "./LinkEditor";

export default function CategoryPage({ id, topic }: { id: number; topic: Topic }) {
  const navigate = useNavigate();
  const { data, error, reload } = useLoad(() => studio.category(id), [id]);
  const [saved, setSaved] = useState(false);
  const remove = useAction();

  if (!data) return error ? <p role="alert">{error}</p> : <p>Loading…</p>;

  function confirmDelete() {
    if (!window.confirm(`Delete the category “${data!.name}”? Its words will be kept.`)) return;
    void remove.run(async () => {
      await studio.deleteCategory(id);
      navigate("/studio/categories");
    });
  }

  return (
    <>
      <h1>{data.name}</h1>
      {error && <p role="alert">{error}</p>}
      <p>
        {data.word_count} {data.word_count === 1 ? "word" : "words"}.
        {data.word_count < 4 && " A category needs at least 4 to be used in a game."}
        {data.word_count === 4 && " One more would let games vary."}
      </p>
      <AddWords categoryId={id} existing={data.words.map((w) => w.text)} onAdded={reload} />
      <table>
        <thead>
          <tr>
            <th>Word</th>
            <th>Meanings</th>
            <th>Difficulty</th>
            <th>Example sentence</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.words.map((w) => (
            <tr key={w.link_id}>
              <td>
                <Link to={`/studio/words/${w.word_id}`}>{w.text}</Link>
              </td>
              <td>{w.meanings}</td>
              <LinkEditor
                linkId={w.link_id}
                name={w.text}
                fields={w}
                inherited={data.difficulty}
                onChange={reload}
              />
            </tr>
          ))}
        </tbody>
      </table>
      <details>
        <summary>Edit category</summary>
        <CategoryForm
          topic={topic}
          initial={data}
          submitLabel="Save category"
          onSubmit={async (fields) => {
            setSaved(false);
            await studio.updateCategory(id, fields);
            await reload();
            setSaved(true);
          }}
        />
        <p role="status">{saved && "Saved."}</p>
        {remove.error && <p role="alert">{remove.error}</p>}
        <button disabled={remove.busy} onClick={confirmDelete}>
          Delete category
        </button>
      </details>
    </>
  );
}
