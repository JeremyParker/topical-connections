import type { Topic } from "../api";

export default function Home({ topic }: { topic: Topic }) {
  return (
    <>
      <h1>{topic.name}</h1>
      <p>The daily game is coming soon.</p>
    </>
  );
}
