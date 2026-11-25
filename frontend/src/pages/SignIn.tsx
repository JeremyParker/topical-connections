import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type User } from "../api";

export default function SignIn({ onSignedIn }: { onSignedIn: (user: User) => void }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (challenge === null) {
        setChallenge((await api.requestCode(email)).challenge);
      } else {
        onSignedIn(await api.verifyCode(challenge, code));
        navigate("/");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function startOver() {
    setChallenge(null);
    setCode("");
    setError("");
  }

  return (
    <form onSubmit={submit}>
      <h1>Sign in</h1>
      {challenge === null ? (
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
      ) : (
        <>
          <p>We emailed a 6-digit code to {email}.</p>
          <label>
            Code
            <input
              key="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              title="6 digits"
              required
              autoFocus
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            />
          </label>
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <button disabled={busy}>{challenge === null ? "Email me a code" : "Sign in"}</button>
      {challenge !== null && (
        <button type="button" onClick={startOver}>
          Start over
        </button>
      )}
    </form>
  );
}
