export type Engagement = {
  id: string;
  name: string;
  proposed_type: string | null;
  proposed_confidence: number | null;
  proposed_reasons: string[];
  missing_evidence: string[];
  scope_status: string;
  scope_audit_type: string | null;
  scope_confirmed_by: string | null;
  scope_confirmed_at: string | null;
  scope_rejected_by: string | null;
  scope_rejected_at: string | null;
  scope_rejection_note: string | null;
  analysis_run_count: number;
  created_by: string;
  created_at: string;
};

export type EvidenceField = {
  id: string;
  document_id: string;
  field_name: string;
  value: string | null;
  page: number | null;
  confidence: number;
  validation_status: string;
  source: string;
};

export type AuditDocument = {
  id: string;
  engagement_id: string;
  filename: string;
  sha256: string;
  page_count: number;
  document_class: string | null;
  class_confidence: number | null;
  class_reasons: string[];
  uploaded_by: string;
  uploaded_at: string;
  fields?: EvidenceField[];
};

export type SamplePack = {
  id: string;
  title: string;
  description: string;
  expected_rules?: string[];
  file_count?: number;
  files?: string[];
};

export type FindingEvidence = {
  id: string;
  document_id: string;
  filename: string;
  field_name: string;
  value: string | null;
  page: number | null;
  validation_status: string;
};

export type Finding = {
  id: string;
  rule_id: string;
  title: string;
  narrative_status: string;
  delta_amount: number | null;
  currency: string | null;
  risk_band: string;
  explanation: string;
  review_status: string;
  review_note: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  detail: Record<string, unknown>;
  evidence: FindingEvidence[];
};

export type AuditUser = {
  id: string;
  email: string;
  name: string;
  role: string;
  active: number;
};

export type AuditEvent = {
  id: number;
  ts_utc: string;
  actor: string;
  action: string;
  object_type: string;
  object_id: string;
  payload: Record<string, unknown>;
  payload_hash: string;
  prev_hash: string;
  chain_hash: string;
};

export function auditActionLabel(action: string): string {
  const labels: Record<string, string> = {
    AUTH_LOGIN: "Signed in",
    AUTH_LOGOUT: "Signed out",
    AUTH_FAILED: "Sign-in failed",
    ENGAGEMENT_CREATED: "Engagement created",
    MEMBERSHIP_GRANTED: "Membership granted",
    DOCUMENT_INGESTED: "Document ingested",
    DOCUMENT_DUPLICATE_SKIPPED: "Duplicate document skipped",
    DOCUMENT_CLASSIFIED: "Document classified",
    EXTRACTION_COMPLETED: "Extraction completed",
    DOCUMENT_VIEWED: "Document viewed",
    DOCUMENT_DOWNLOADED: "Document downloaded",
    EVIDENCE_VIEWED: "Evidence viewed",
    SCOPE_CONFIRMED: "Scope confirmed",
    SCOPE_REJECTED: "Scope rejected",
    SCOPE_REOPENED: "Scope reopened",
    ANALYSIS_STARTED: "Analysis started",
    ANALYSIS_COMPLETED: "Analysis completed",
    FINDINGS_VIEWED: "Findings viewed",
    FINDING_APPROVED: "Finding approved",
    FINDING_CORRECTED: "Finding corrected",
    FINDING_REJECTED: "Finding rejected",
    EXPORT_CREATED: "Export created",
    MODEL_CALL: "Model call",
    USER_CREATED: "User created",
    USER_UPDATED: "User updated",
    RETENTION_UPDATED: "Retention updated",
  };
  return labels[action] ?? action.replaceAll("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

export function auditEventDetail(event: AuditEvent): string {
  const payload = event.payload ?? {};
  const parts: string[] = [];
  if (typeof payload.title === "string") parts.push(payload.title);
  if (typeof payload.rule_id === "string") parts.push(payload.rule_id);
  if (typeof payload.filename === "string") parts.push(payload.filename);
  if (typeof payload.document_class === "string") parts.push(String(payload.document_class).replaceAll("_", " "));
  if (typeof payload.audit_type === "string") parts.push(String(payload.audit_type).replaceAll("_", " "));
  if (typeof payload.prior_scope_status === "string") parts.push(`was ${String(payload.prior_scope_status)}`);
  if (typeof payload.note === "string" && payload.note.trim()) parts.push(`Note: ${payload.note}`);
  if (typeof payload.finding_count === "number") parts.push(`${payload.finding_count} findings`);
  if (typeof payload.field_count === "number") parts.push(`${payload.field_count} fields`);
  if (typeof payload.document_count === "number") parts.push(`${payload.document_count} documents`);
  if (typeof payload.email === "string" && event.action.includes("MEMBER")) parts.push(payload.email);
  if (typeof payload.role === "string" && event.action.startsWith("USER_")) parts.push(String(payload.role).replaceAll("_", " "));
  if (typeof payload.prior_review_status === "string" && payload.prior_review_status !== "open") {
    parts.push(`was ${String(payload.prior_review_status)}`);
  }
  return parts.join(" · ");
}

const FIELD_LABELS: Record<string, string> = {
  invoice_id: "Invoice ID",
  vendor: "Vendor",
  invoice_date: "Invoice date",
  amount: "Amount",
  tax: "Tax",
  po_reference: "PO reference",
  approval_status: "Approval status",
  po_number: "PO number",
  po_date: "PO date",
  approved_by: "Approved by",
  payment_id: "Payment ID",
  payment_date: "Payment date",
  reference: "Reference",
  policy_name: "Policy name",
  spending_limit: "Spending limit",
  approval_required_above: "Approval required above",
};

export function fieldLabel(name: string): string {
  return FIELD_LABELS[name] ?? name.replaceAll("_", " ");
}

export function classLabel(value: string | null): string {
  if (value === "purchase_order") return "Purchase order";
  if (value === "invoice") return "Invoice";
  if (value === "payment") return "Payment";
  if (value === "policy") return "Policy";
  if (value === "procurement_financial") return "Procurement financial";
  if (!value || value === "unknown") return "Unknown";
  return value;
}

export function formatEngagementDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

const STATUS_LABELS: Record<string, string> = {
  validated: "Validated",
  failed: "Failed",
  not_found: "Not found",
  unverified: "Unverified",
  proposed: "Proposed",
  confirmed: "Confirmed",
  rejected: "Rejected",
  open: "Open",
  approved: "Approved",
  corrected: "Corrected",
  low: "Low",
  medium: "Medium",
  high: "High",
};

export function statusLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return STATUS_LABELS[value] ?? value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function formatPkr(amount: number | null): string {
  if (amount === null || Number.isNaN(amount)) return "—";
  const sign = amount < 0 ? "-" : "";
  return `${sign}PKR ${Math.abs(amount).toLocaleString("en-US")}`;
}
