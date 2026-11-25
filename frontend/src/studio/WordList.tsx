import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MAX_WORD_LENGTH, studio } from "./api";
import { useAction, useLoad } from "./hooks";
import ListControls, { useListParams } from "./ListControls";

export default function WordList() {
  const navigate = useNavigate();
  const list = useListParams();
  const { search, only, offset } = list;
  const { data, error } = useLoad(
    () => studio.words({ search, only, offset }),
    [search, only, offset],
  );
  const [text, setText] = useState("");
  const create = useAction();

  function submit(event: FormEvent) {
    event.preventDefault();
    void create.run(async () => {
      const { id } = await studio.createWord(text);
      navigate(`/studio/words/${id}`);
    });
  }

  return (
    <>
      <h1>Words</h1>
      <details>
        <summary>New word</summary>
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
          {create.error && <p role="alert">{create.error}</p>}
          <button disabled={create.busy}>Create word</button>
        </form>
      </details>
      <ListControls
        {...list}
        label="Search words"
        filters={{ one_meaning: "Only one meaning" }}
        total={data?.total}
      >
        {error && <p role="alert">{error}</p>}
        <table>
          <thead>
            <tr>
              <th>Word</th>
              <th>Categories</th>
              <th>Topical</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((w) => (
              <tr key={w.id}>
                <td>
                  <Link to={`/studio/words/${w.id}`}>{w.text}</Link>
                </td>
                <td>{w.categories.map((c) => c.name).join(", ") || "None"}</td>
                <td>{w.is_topical ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ListControls>
    </>
  );
}
