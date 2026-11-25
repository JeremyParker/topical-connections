import { useState } from "react";
import { type LinkFields, studio } from "./api";
import { DifficultySelect } from "./CategoryForm";
import { useAction } from "./hooks";

type Props = {
  linkId: number;
  name: string; // what the link leads to, for screen readers
  fields: LinkFields;
  inherited: number;
  onChange: () => Promise<unknown>;
};

/** Table cells for editing one word's membership of one category. */
export default function LinkEditor({ linkId, name, fields, inherited, onChange }: Props) {
  const saved = fields.example_sentence ?? "";
  const [example, setExample] = useState(saved);
  const { busy, error, run } = useAction();

  const save = (action: Promise<unknown>) => run(() => action.then(onChange));

  return (
    <>
      <td>
        <DifficultySelect
          label={`Difficulty of ${name}`}
          value={fields.difficulty_override}
          inherited={inherited}
          onChange={(value) => save(studio.updateLink(linkId, { difficulty_override: value }))}
        />
      </td>
      <td>
        <input
          aria-label={`Example sentence for ${name}`}
          placeholder="Optional"
          maxLength={2000}
          value={example}
          onChange={(e) => setExample(e.target.value)}
          onBlur={() => {
            if (example !== saved) {
              void save(studio.updateLink(linkId, { example_sentence: example || null }));
            }
          }}
        />
        {error && <p role="alert">{error}</p>}
      </td>
      <td>
        <button
          disabled={busy}
          aria-label={`Remove ${name}`}
          onClick={() => save(studio.deleteLink(linkId))}
        >
          Remove
        </button>
      </td>
    </>
  );
}
