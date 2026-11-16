export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export type Person = {
  email: string;
  name: string;
  designation: string;
  role: string;
  isAdmin: boolean;
};

export type Citation = {
  label: string;
  text: string;
  image?: string;
};

export type AskResponse = {
  answer: string;
  outcome: string;
  citations: Citation[];
};

export type PolicyRow = {
  id: string;
  title: string;
  audience: string;
  who: string;
  starts_on: string;
  ends_on?: string | null;
  filename?: string;
};

export type QuestionRow = {
  id: string;
  question: string;
  asked_by: string;
  outcome_label: string;
  policy: string;
  when: string;
  steps: { label: string; detail: string }[];
  technical: Record<string, unknown>;
};

export type CheckRow = {
  name: string;
  ok: boolean;
  primary: boolean;
  developer_detail: string;
};

export type ChecksResponse = {
  status: string;
  summary: string;
  ran_at: string | null;
  checks: CheckRow[];
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError("The assistant is not available right now. Try again in a moment.", 0);
  }
  const data = (await response.json().catch(() => ({}))) as { message?: string };
  if (!response.ok) {
    throw new ApiError(data.message || "Something went wrong. Try again.", response.status);
  }
  return data as T;
}

export function formatWhen(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 45) return "Just now";
  if (seconds < 3600) {
    const minutes = Math.max(1, Math.round(seconds / 60));
    return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  }
  if (seconds < 86400) {
    const hours = Math.round(seconds / 3600);
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  return new Date(iso).toLocaleString();
}
