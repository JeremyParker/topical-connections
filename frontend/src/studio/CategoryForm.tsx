import { type FormEvent, useState } from "react";
import type { Topic } from "../api";
import { type CategoryFields, DIFFICULTIES } from "./api";
import { useAction } from "./hooks";

type Props = {
  topic: Topic;
  initial?: CategoryFields;
  submitLabel: string;
  onSubmit: (fields: CategoryFields) => Promise<unknown>;
};

export default function CategoryForm({ topic, initial, submitLabel, onSubmit }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [difficulty, setDifficulty] = useState(initial?.difficulty ?? 1);
  const [isTopical, setIsTopical] = useState(initial?.is_topical ?? false);
  const { busy, error, run } = useAction();

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(() => onSubmit({ name, notes: notes || null, difficulty, is_topical: isTopical }));
  }

  return (
    <form onSubmit={submit}>
      <label>
        Category name
        <input required maxLength={256} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <div className="row">
        <label>
          Difficulty
          <DifficultySelect value={difficulty} onChange={(value) => setDifficulty(value ?? 1)} />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={isTopical}
            onChange={(e) => setIsTopical(e.target.checked)}
          />
          {topic.topical_label}
        </label>
      </div>
      <label>
        Notes for contributors
        <textarea
          rows={2}
          maxLength={2000}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>
      {error && <p role="alert">{error}</p>}
      <button disabled={busy}>{submitLabel}</button>
    </form>
  );
}

type SelectProps = {
  value: number | null;
  onChange: (value: number | null) => void;
  inherited?: number; // offers "same as the category" when given
  label?: string;
};

export function DifficultySelect({ value, onChange, inherited, label }: SelectProps) {
  return (
    <select
      aria-label={label}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
    >
      {inherited !== undefined && <option value="">Same ({DIFFICULTIES[inherited]})</option>}
      {DIFFICULTIES.map((text, i) => (
        <option key={text} value={i}>
          {text}
        </option>
      ))}
    </select>
  );
}
