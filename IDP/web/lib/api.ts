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
        if (item && typeof item === "object" && "msg" in item) return String((item as { msg: unknown }).msg);
        return String(item);
      })
      .join(" ");
  }
  return fallback;
}

const ACTOR_KEY = "idp_actor";

export function readActor(): string {
  if (typeof window === "undefined") return "finance_user";
  return (localStorage.getItem(ACTOR_KEY) || "finance_user").trim() || "finance_user";
}

export function writeActor(value: string): void {
  localStorage.setItem(ACTOR_KEY, value.trim());
}

function headers(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  h.set("X-Actor", readActor());
  return h;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const h = headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !h.has("Content-Type")) {
    h.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_URL}${path}`, { ...options, headers: h });
  if (!response.ok) {
    let message = response.statusText;
    try {
      message = detailMessage(await response.json(), message);
    } catch {
      // ignore
    }
    throw new ApiError(message || "Request failed", response.status);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return undefined as T;
  return (await response.json()) as T;
}

export async function uploadFile(file: File): Promise<JobDetail> {
  const body = new FormData();
  body.append("file", file);
  return api<JobDetail>("/api/jobs/upload", { method: "POST", body });
}

export async function downloadExport(jobId: string, fmt: "csv" | "xlsx" | "result" = "csv"): Promise<void> {
  const response = await fetch(`${API_URL}/api/jobs/${jobId}/download?fmt=${fmt}`, {
    headers: headers(),
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      message = detailMessage(await response.json(), message);
    } catch {
      // ignore
    }
    throw new ApiError(message || "Download failed", response.status);
  }
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  const ext = fmt === "xlsx" ? "xlsx" : "csv";
  link.download = fmt === "result" ? `${jobId}-result.csv` : `${jobId}-erp.${ext}`;
  link.click();
  URL.revokeObjectURL(href);
}

export type StageId = "upload" | "analyze" | "clean" | "validate" | "approve" | "export";

export type JobSummary = {
  id: string;
  filename: string;
  content_type: string | null;
  status: string;
  stage: StageId;
  source_kind: string | null;
  created_at: string;
  updated_at: string;
  sha256: string;
};

export type IdpException = {
  id: string;
  code: string;
  severity: string;
  message: string;
  row_index: number | null;
  field_name: string | null;
  value: unknown;
  status: string;
  decision_note: string | null;
  decided_at: string | null;
};

export type AuditEvent = {
  id: number;
  event: string;
  actor: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type JobDetail = {
  id: string;
  filename: string;
  content_type: string | null;
  sha256: string;
  status: string;
  stage: StageId;
  source_kind: string | null;
  created_at: string;
  updated_at: string;
  error: string | null;
  raw_preview: Record<string, unknown>;
  analysis: Record<string, unknown>;
  cleaned: {
    columns?: string[];
    rows?: Record<string, unknown>[];
    row_count?: number;
    stats?: Record<string, number>;
    options?: {
      drop_blank_rows?: boolean;
      drop_blank_keys?: boolean;
      dedupe_keys?: boolean;
      drop_exact_duplicates?: boolean;
      rename_erp?: boolean;
      trim_whitespace?: boolean;
      nullify_placeholders?: boolean;
      normalize_numbers?: boolean;
      standardize_dates?: boolean;
      lowercase_emails?: boolean;
      uppercase_ids?: boolean;
    };
    result_path?: string;
    remediations?: {
      summary?: string;
      steps_considered?: string[];
      notes_considered?: { note?: string; code?: string; row_index?: number | null }[];
      applied?: { action?: string; field?: string; row_index?: number | null; reason?: string; status?: string }[];
      changes_applied?: number;
      rows_dropped?: number;
    };
  };
  validation: {
    ok?: boolean;
    exception_count?: number;
    summary?: Record<string, unknown>;
    review_checklist?: {
      focus?: string[];
      likely_keys?: string[];
      erp_risks?: string[];
      summary?: string;
      advisory_only?: boolean;
    };
  };
  export_path: string | null;
  export_formats?: string[];
  xlsx_skipped_reason?: string | null;
  exceptions: IdpException[];
  audit_trail: AuditEvent[];
  stages: StageId[];
};

export const STAGES: { id: StageId; label: string }[] = [
  { id: "upload", label: "Receive" },
  { id: "analyze", label: "Overview" },
  { id: "clean", label: "Prepare" },
  { id: "validate", label: "Findings" },
  { id: "approve", label: "Decide" },
  { id: "export", label: "Download" },
];

export function stageIndex(stage: string): number {
  const idx = STAGES.findIndex((s) => s.id === stage);
  return idx < 0 ? 0 : idx;
}
