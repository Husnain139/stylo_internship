import { STAGES, stageIndex, type JobDetail, type StageId } from "@/lib/api";

const STATUS_LABELS: Record<string, string> = {
  uploaded: "File received",
  analyzing: "Reading the document…",
  awaiting_clean: "Choose what to fix",
  cleaning: "Fixing the file…",
  validating: "Checking for issues…",
  awaiting_approval: "Findings need your review",
  ready_to_export: "Ready to download",
  blocked_rejections: "Blocked — some findings sent back",
  exported: "Finished",
  failed: "Could not finish",
  pending: "Needs review",
  approved: "Accepted",
  rejected: "Sent back",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status.replace(/_/g, " ");
}

export function statusClass(status: string): string {
  return `pill status-${status.replace(/[^a-z0-9_]/gi, "_")}`;
}

export function stageLabel(stage: string): string {
  return STAGES.find((s) => s.id === stage)?.label || stage;
}

export function nextAction(detail: JobDetail): string {
  const pending = detail.exceptions.filter((e) => e.status === "pending").length;
  switch (detail.status) {
    case "analyzing":
      return "Looking over the document for key facts…";
    case "awaiting_clean":
      return "Choose what blanks and duplicates to fix";
    case "cleaning":
      return "Removing blanks and duplicates…";
    case "validating":
      return "Looking for inconsistencies…";
    case "awaiting_approval":
      return pending
        ? `Review ${pending} finding${pending === 1 ? "" : "s"}`
        : "Continue to finish & download";
    case "ready_to_export":
      return "Download the finished file";
    case "blocked_rejections":
      return "Resolve sent-back findings before download";
    case "exported":
      return "Download CSV or spreadsheet";
    case "failed":
      return detail.error || "Fix the problem and upload again";
    default:
      if (detail.stage === "upload") return "Continue to document overview";
      if (detail.stage === "analyze") return "Continue to prepare the file";
      return "Continue to the next step";
  }
}

export function continueTarget(
  fromStage: StageId,
  detail: JobDetail,
): { stage: StageId; label: string } | null {
  const progress = stageIndex(detail.stage);
  const pending = detail.exceptions.some((e) => e.status === "pending");
  const hasExceptions = detail.exceptions.length > 0;

  if (fromStage === "clean" && progress >= stageIndex("validate")) {
    return { stage: "validate", label: "Continue to Findings →" };
  }
  if (fromStage === "validate" && progress >= stageIndex("approve")) {
    if (hasExceptions && (pending || detail.status === "awaiting_approval" || progress < stageIndex("export"))) {
      return { stage: "approve", label: "Continue to Review & decide →" };
    }
    if (progress >= stageIndex("export") || detail.status === "ready_to_export" || detail.status === "exported") {
      return { stage: "export", label: "Continue to Finish & download →" };
    }
    return { stage: "approve", label: "Continue to Review & decide →" };
  }
  if (fromStage === "approve") {
    if (pending) return null;
    if (progress >= stageIndex("export") || detail.status === "ready_to_export" || detail.status === "exported") {
      return { stage: "export", label: "Continue to Finish & download →" };
    }
  }
  return null;
}

/** Pager next-button copy when the natural flow step has a purpose label. */
export function pagerNextLabel(viewStage: StageId, nextStage: StageId, detail: JobDetail): string {
  const target = continueTarget(viewStage, detail);
  if (target && target.stage === nextStage) return target.label;
  return `${stageLabel(nextStage)} →`;
}

export function formatUpdatedAt(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 45) return "Just now";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  if (seconds < 86400 * 7) return `${Math.round(seconds / 86400)}d ago`;
  return new Date(iso).toLocaleString();
}

export function exportBlockedReason(detail: JobDetail): string | null {
  if (detail.status === "awaiting_approval") {
    const pending = detail.exceptions.filter((e) => e.status === "pending").length;
    return pending
      ? `Download is blocked until you review ${pending} finding${pending === 1 ? "" : "s"}.`
      : "Download is blocked until findings are reviewed.";
  }
  if (detail.status === "blocked_rejections") {
    return "Download is blocked because one or more findings were sent back.";
  }
  if (detail.status === "awaiting_clean" || detail.status === "cleaning") {
    return "Finish preparing the file and checking for issues before download.";
  }
  return null;
}

/** Plain-language value kind for auditors (hides raw dtype codes). */
export function valueKindLabel(dtype: string | undefined | null): string {
  switch ((dtype || "").toLowerCase()) {
    case "currency":
    case "number":
      return "Amount / number";
    case "date":
      return "Date";
    case "email":
      return "Email";
    case "boolean":
      return "Yes / No";
    default:
      return "Text";
  }
}

/** Quiet label for exception machine codes. */
export function findingCodeLabel(code: string): string {
  const map: Record<string, string> = {
    DUPLICATE_KEY: "Duplicate",
    MISSING_KEY_VALUE: "Blank key",
    MISSING_KEY_COLUMN: "Missing key field",
    INVALID_NUMBER: "Bad amount",
    INVALID_DATE: "Bad date",
    INVALID_EMAIL: "Bad email",
    INVALID_BOOLEAN: "Bad yes/no",
    EMPTY_DATASET: "No rows left",
    NO_COLUMNS: "No fields found",
  };
  return map[code] || code.replace(/_/g, " ").toLowerCase();
}

export function auditEventLabel(event: string): string {
  const map: Record<string, string> = {
    file_uploaded: "File uploaded",
    stage_analyze_started: "Started reading the document",
    stage_analyze_completed: "Finished document overview",
    stage_clean_awaiting: "Waiting for prepare choices",
    stage_clean_started: "Started fixing blanks & duplicates",
    stage_clean_completed: "Finished preparing the file",
    stage_validate_completed: "Finished checking for issues",
    exception_decided: "Finding decided",
    exceptions_cleared: "All findings cleared",
    export_blocked: "Download blocked",
    stage_export_completed: "Finished file created",
    remediation_applied: "Fixes from notes applied",
    remediation_failed: "Could not apply note fixes",
    pipeline_failed: "Process failed",
  };
  return map[event] || event.replace(/_/g, " ");
}
