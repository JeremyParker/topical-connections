const BASE = import.meta.env.VITE_API_BASE ?? "";

export type Topic = { name: string; topical_label: string };
export type User = {
  email: string;
  display_name: string | null;
  role: "player" | "contributor" | "admin";
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}/api${path}`, {
      method,
      credentials: "include",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "We couldn't reach the server. Please try again.");
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // Validation errors have a list here rather than a message.
    const detail = data?.detail;
    throw new ApiError(
      response.status,
      typeof detail === "string" ? detail : "Something went wrong. Please check what you entered.",
    );
  }
  return data as T;
}

export const api = {
  topic: () => call<Topic>("GET", "/topic"),
  me: () =>
    call<User>("GET", "/auth/me").catch((e) => {
      if (e instanceof ApiError && e.status === 401) return null;
      throw e;
    }),
  requestCode: (email: string) => call<{ challenge: string }>("POST", "/auth/code", { email }),
  verifyCode: (challenge: string, code: string) =>
    call<User>("POST", "/auth/verify", { challenge, code }),
  logout: () => call<void>("POST", "/auth/logout"),
};
