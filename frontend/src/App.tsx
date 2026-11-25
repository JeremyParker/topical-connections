import { lazy, Suspense, useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { api, type Topic, type User } from "./api";
import Home from "./pages/Home";
import SignIn from "./pages/SignIn";

// Loaded only when needed, so players don't download it.
const Studio = lazy(() => import("./pages/Studio"));

export default function App() {
  const [topic, setTopic] = useState<Topic | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.topic(), api.me()])
      .then(([topic, user]) => {
        document.title = topic.name;
        setTopic(topic);
        setUser(user);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  async function signOut() {
    try {
      await api.logout();
      setUser(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!topic) return <main>{error ? <p role="alert">{error}</p> : <p>Loading…</p>}</main>;

  const canEdit = user !== null && user.role !== "player";
  return (
    <>
      <header>
        <Link to="/" className="name">
          {topic.name}
        </Link>
        <nav>
          {canEdit && <Link to="/studio">Studio</Link>}
          {user ? (
            <button onClick={signOut}>Sign out</button>
          ) : (
            <Link to="/sign-in">Sign in</Link>
          )}
        </nav>
      </header>
      <main>
        {error && <p role="alert">{error}</p>}
        <Suspense fallback={<p>Loading…</p>}>
          <Routes>
            <Route path="/" element={<Home topic={topic} />} />
            <Route path="/sign-in" element={<SignIn onSignedIn={setUser} />} />
            <Route
              path="/studio"
              element={canEdit ? <Studio /> : <p>The studio is for contributors.</p>}
            />
            <Route path="*" element={<p>Page not found.</p>} />
          </Routes>
        </Suspense>
      </main>
    </>
  );
}
