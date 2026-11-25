import { Link, useNavigate } from "react-router-dom";
import type { Topic } from "../api";
import { DIFFICULTIES, studio } from "./api";
import CategoryForm from "./CategoryForm";
import { useLoad } from "./hooks";
import ListControls, { useListParams } from "./ListControls";

const FILTERS = {
  needs_words: "Needs more words",
  topical: "Topical",
  not_topical: "Not topical",
};

export default function CategoryList({ topic }: { topic: Topic }) {
  const navigate = useNavigate();
  const list = useListParams();
  const { search, only, offset } = list;
  const { data, error } = useLoad(
    () => studio.categories({ search, only, offset }),
    [search, only, offset],
  );

  return (
    <>
      <h1>Categories</h1>
      <details>
        <summary>New category</summary>
        <CategoryForm
          topic={topic}
          submitLabel="Create category"
          onSubmit={async (fields) => {
            const { id } = await studio.createCategory(fields);
            navigate(`/studio/categories/${id}`);
          }}
        />
      </details>
      <ListControls {...list} label="Search categories" filters={FILTERS} total={data?.total}>
        {error && <p role="alert">{error}</p>}
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th>Words</th>
              <th>Difficulty</th>
              <th>Topical</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id}>
                <td>
                  <Link to={`/studio/categories/${c.id}`}>{c.name}</Link>
                </td>
                <td>{c.word_count < 4 ? `${c.word_count} (needs more)` : c.word_count}</td>
                <td>{DIFFICULTIES[c.difficulty]}</td>
                <td>{c.is_topical ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ListControls>
    </>
  );
}
