import { clearSession, readSession } from "./session";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function detailMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) return String(item.msg);
        return String(item);
      })
      .join(" ");
  }
  return fallback;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const session = readSession();
  if (session) headers.set("Authorization", `Bearer ${session.token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (response.status === 401 && path !== "/auth/login") {
    clearSession();
  }
  if (!response.ok) {
    let message = response.statusText;
    try {
      message = detailMessage(await response.json(), message);
    } catch {
      // The body was not JSON.
    }
    throw new ApiError(message || "Request failed", response.status);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return undefined as T;
  return (await response.json()) as T;
}

export async function fetchPdfUrl(documentId: string): Promise<string> {
  const session = readSession();
  const response = await fetch(`${API_URL}/documents/${documentId}/file`, {
    headers: session ? { Authorization: `Bearer ${session.token}` } : {},
  });
  if (!response.ok) {
    throw new ApiError("The PDF could not be loaded", response.status);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export async function downloadExport(engagementId: string): Promise<void> {
  const session = readSession();
  const response = await fetch(`${API_URL}/engagements/${engagementId}/export`, {
    headers: session ? { Authorization: `Bearer ${session.token}` } : {},
  });
  if (!response.ok) {
    throw new ApiError("Export is not available for this role", response.status);
  }
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = `${engagementId}-findings.json`;
  link.click();
  URL.revokeObjectURL(href);
}
