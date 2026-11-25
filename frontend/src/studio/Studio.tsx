import { NavLink, Route, Routes, useParams } from "react-router-dom";
import type { Topic } from "../api";
import CategoryList from "./CategoryList";
import CategoryPage from "./CategoryPage";
import Overview from "./Overview";
import "./studio.css";
import WordList from "./WordList";
import WordPage from "./WordPage";

export default function Studio({ topic }: { topic: Topic }) {
  return (
    <div className="studio">
      <nav aria-label="Studio">
        <NavLink to="/studio" end>
          Overview
        </NavLink>
        <NavLink to="/studio/categories">Categories</NavLink>
        <NavLink to="/studio/words">Words</NavLink>
      </nav>
      <Routes>
        <Route index element={<Overview />} />
        <Route path="categories" element={<CategoryList topic={topic} />} />
        <Route path="categories/:id" element={<KeyedCategory topic={topic} />} />
        <Route path="words" element={<WordList />} />
        <Route path="words/:id" element={<KeyedWord topic={topic} />} />
        <Route path="*" element={<p>Page not found.</p>} />
      </Routes>
    </div>
  );
}

// The keys start each page afresh when moving straight from one item to another.
function KeyedCategory({ topic }: { topic: Topic }) {
  const id = Number(useParams().id);
  return <CategoryPage key={id} id={id} topic={topic} />;
}

function KeyedWord({ topic }: { topic: Topic }) {
  const id = Number(useParams().id);
  return <WordPage key={id} id={id} topic={topic} />;
}
