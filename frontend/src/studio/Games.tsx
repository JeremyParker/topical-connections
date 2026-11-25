import { useEffect, useRef, useState } from "react";
import { type Candidate, DIFFICULTIES, type Game, studio } from "./api";
import { useAction, useLoad } from "./hooks";

const PAGE_SIZE = 50;
const BATCH = 10;
const SCORE_LABELS: Record<string, string> = {
  decoys: "Decoys",
  red_herrings: "Red herrings",
  difficulty: "Difficulty spread",
  topical_mix: "Topical mix",
  freshness: "Freshness",
};

export default function Games() {
  const [offset, setOffset] = useState(0);
  const { data, error, reload } = useLoad(() => studio.candidates({ offset }), [offset]);
  const [message, setMessage] = useState("");
  const { busy, error: failed, run } = useAction();
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  function generate() {
    void run(async () => {
      setMessage("");
      let job = await studio.generate(BATCH);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        if (!mounted.current) return;
        job = await studio.job(job.id);
      }
      if (job.status === "failed") throw new Error(job.error ?? "Something went wrong.");
      const created = job.result?.created ?? 0;
      setMessage(job.result?.problem ?? `${created} new ${created === 1 ? "game" : "games"}.`);
      await reload();
    });
  }

  return (
    <>
      <h1>Games</h1>
      <p>Generated games waiting for review, best score first. Answers stay hidden until opened.</p>
      <div className="row">
        <button disabled={busy} onClick={generate}>
          {busy ? "Generating…" : `Generate ${BATCH} games`}
        </button>
      </div>
      <p role="status">{message}</p>
      {(failed || error) && <p role="alert">{failed || error}</p>}
      {data?.items.map((c) => (
        <CandidateCard key={c.id} candidate={c} />
      ))}
      {data && (
        <div className="row">
          <span className="grow">{data.total === 0 ? "No games yet." : `${data.total} games`}</span>
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <button
            disabled={offset + PAGE_SIZE >= data.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      )}
    </>
  );
}

function CandidateCard({ candidate }: { candidate: Candidate }) {
  const { game } = candidate;
  return (
    <section>
      <h2>
        Game {candidate.id}: {Math.round(candidate.score)} points
      </h2>
      <ul className="board">
        {boardOrder(game).map((word) => (
          <li key={word.word_id}>{word.text}</li>
        ))}
      </ul>
      <details>
        <summary>Show answers</summary>
        <Answers game={game} />
      </details>
    </section>
  );
}

/** A fixed order that doesn't give the groups away, as ids follow entry order. */
function boardOrder(game: Game) {
  const key = (id: number) => Math.imul(id, 2654435761) >>> 0;
  return game.groups
    .flatMap((group) => group.words)
    .sort((a, b) => key(a.word_id) - key(b.word_id));
}

function Answers({ game }: { game: Game }) {
  return (
    <ul>
      {game.groups.map((group) => (
        <li key={group.category_id}>
          <strong>{group.name}</strong> ({DIFFICULTIES[group.difficulty]}
          {group.is_topical && ", topical"}): {group.words.map((w) => w.text).join(", ")}
        </li>
      ))}
      {game.decoys.map((d) => (
        <li key={d.word}>
          Decoy: {d.word} also fits {d.also_fits.join(", ")}
        </li>
      ))}
      {game.red_herrings.map((h) => (
        <li key={h.name}>
          Red herring: {h.words.join(", ")} all fit {h.name}
        </li>
      ))}
      <li>
        {Object.entries(game.scores)
          .map(([name, points]) => `${SCORE_LABELS[name] ?? name} ${points}`)
          .join(", ")}
      </li>
    </ul>
  );
}
