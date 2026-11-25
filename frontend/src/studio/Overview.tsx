import { Link } from "react-router-dom";
import { studio } from "./api";
import { useLoad } from "./hooks";

export default function Overview() {
  const { data, error } = useLoad(studio.summary, []);
  const { data: suggestions } = useLoad(studio.suggestions, []);
  if (!data) return error ? <p role="alert">{error}</p> : <p>Loading…</p>;
  return (
    <>
      <h1>Studio</h1>
      <p>
        {data.words} words, {data.categories} categories and {data.links} links between them.
      </p>
      <ul>
        <li>{data.usable_categories} categories have at least 4 words, so games can use them.</li>
        <li>
          <Link to="/studio/categories?only=needs_words">
            {data.categories_needing_words} categories need more words
          </Link>
        </li>
        <li>
          <Link to="/studio/words?only=one_meaning">
            {data.words_with_one_meaning} words have only one meaning
          </Link>
        </li>
      </ul>
      <Suggested
        title="One word short of being usable"
        categories={suggestions?.almost_usable ?? []}
      />
      <Suggested
        title="Usable, but sharing no words with other usable categories"
        categories={suggestions?.isolated ?? []}
      />
      {data.categories === 0 && (
        <p>
          To begin, <Link to="/studio/categories">create a category</Link> and paste in some words.
        </p>
      )}
    </>
  );
}

type SuggestedProps = { title: string; categories: { id: number; name: string }[] };

function Suggested({ title, categories }: SuggestedProps) {
  if (categories.length === 0) return null;
  return (
    <section>
      <h2>{title}</h2>
      <ul>
        {categories.map((c) => (
          <li key={c.id}>
            <Link to={`/studio/categories/${c.id}`}>{c.name}</Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
