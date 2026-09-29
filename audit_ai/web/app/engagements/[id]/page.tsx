"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { classLabel, formatEngagementDate, statusLabel, type AuditDocument, type Engagement, type SamplePack } from "@/lib/types";

export default function OverviewPage() {
  const params = useParams<{ id: string }>();
  const [engagement, setEngagement] = useState<Engagement | null>(null);
  const [documents, setDocuments] = useState<AuditDocument[]>([]);
  const [packs, setPacks] = useState<SamplePack[]>([]);
  const [packId, setPackId] = useState("mismatch");
  const [error, setError] = useState("");
  const [pending, setPending] = useState("");
  const [rejectNote, setRejectNote] = useState("");
  const role = useSession()?.role;

  const reload = useCallback(async () => {
    const nextEngagement = await api<Engagement>(`/engagements/${params.id}`);
    setEngagement(nextEngagement);
    try {
      setDocuments(await api<AuditDocument[]>(`/engagements/${params.id}/documents`));
    } catch (reason) {
      setDocuments([]);
      setError(reason instanceof Error ? reason.message : "Documents are not available for this role");
    }
  }, [params.id]);

  useEffect(() => {
    let cancelled = false;
    api<Engagement>(`/engagements/${params.id}`)
      .then((nextEngagement) => {
        if (!cancelled) setEngagement(nextEngagement);
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      });
    api<AuditDocument[]>(`/engagements/${params.id}/documents`)
      .then((nextDocuments) => {
        if (!cancelled) setDocuments(nextDocuments);
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setDocuments([]);
          setError(reason.message);
        }
      });
    api<SamplePack[]>("/sample-packs")
      .then((nextPacks) => {
        if (cancelled) return;
        setPacks(nextPacks);
        if (nextPacks.length && !nextPacks.some((pack) => pack.id === packId)) {
          setPackId(nextPacks[0].id);
        }
      })
      .catch(() => {
        if (!cancelled) setPacks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  async function run(label: string, task: () => Promise<unknown>) {
    setPending(label);
    setError("");
    try {
      await task();
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Request failed");
    } finally {
      setPending("");
    }
  }

  return (
    <div className="stack">
      <section className="banner">
        <strong>Scope is a human decision</strong>
        The classifier only proposes a procurement review. A senior auditor on this engagement confirms that scope, or rejects it with a reason. Rejection freezes document uploads until that senior reopens the scope. Junior auditors and administrators do not make this decision.
      </section>
      {engagement ? (
        <section className="panel scope-panel">
          <div className="scope-section">
            <div className="scope-meta">
              <div>
                <span className="scope-label">Status</span>
                <span className={`pill pill-${engagement.scope_status}`}>{statusLabel(engagement.scope_status)}</span>
              </div>
              <div>
                <span className="scope-label">Proposed type</span>
                <strong>
                  {engagement.proposed_type ? classLabel(engagement.proposed_type) : "Not enough documents yet"}
                </strong>
              </div>
              <div>
                <span className="scope-label">Confidence</span>
                <strong>
                  {engagement.proposed_confidence !== null
                    ? `${Math.round(engagement.proposed_confidence * 100)}%`
                    : "—"}
                </strong>
              </div>
            </div>
          </div>
          <div className="scope-section">
            <p className="scope-label">Classification</p>
            <ul className="scope-list">
              {(engagement.proposed_reasons.length
                ? engagement.proposed_reasons
                : ["Upload documents to propose a scope."]
              ).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
          <div className="scope-section">
            <p className="scope-label">File set</p>
            <p className="scope-body">
              {!engagement.proposed_type
                ? "No documents have been classified yet."
                : engagement.missing_evidence.length
                  ? `Missing: ${engagement.missing_evidence.map(classLabel).join(", ")}`
                  : "Nothing required for the procurement pack."}
            </p>
          </div>
          {engagement.scope_status === "confirmed" ? (
            <div className="scope-section scope-decision">
              <p className="scope-label">Decision</p>
              <p className="scope-body">
                Confirmed by {engagement.scope_confirmed_by} on{" "}
                {engagement.scope_confirmed_at ? formatEngagementDate(engagement.scope_confirmed_at) : "—"} as{" "}
                {classLabel(engagement.scope_audit_type)}.
              </p>
            </div>
          ) : (
            <div className="scope-section scope-decision">
              <p className="scope-label">Decision</p>
              {engagement.scope_status === "rejected" ? (
                <p className="scope-body">
                  Rejected by {engagement.scope_rejected_by} on{" "}
                  {engagement.scope_rejected_at ? formatEngagementDate(engagement.scope_rejected_at) : "—"}. Reason:{" "}
                  {engagement.scope_rejection_note}
                </p>
              ) : null}
              {role === "senior_auditor" ? (
                <div className="scope-actions">
                  <div className="decision-actions">
                    <button
                      type="button"
                      disabled={Boolean(pending) || engagement.proposed_type !== "procurement_financial"}
                      onClick={() =>
                        run("confirm", () =>
                          api(`/engagements/${params.id}/confirm-scope`, {
                            method: "POST",
                            body: JSON.stringify({ audit_type: "procurement_financial" }),
                          }),
                        )
                      }
                    >
                      {pending === "confirm" ? "Confirming…" : "Confirm procurement scope"}
                    </button>
                    <button
                      className="danger"
                      type="button"
                      disabled={Boolean(pending) || !rejectNote.trim()}
                      onClick={() =>
                        run("reject", async () => {
                          await api(`/engagements/${params.id}/reject-scope`, {
                            method: "POST",
                            body: JSON.stringify({ note: rejectNote.trim() }),
                          });
                          setRejectNote("");
                        })
                      }
                    >
                      {pending === "reject" ? "Rejecting…" : "Reject proposed scope"}
                    </button>
                  </div>
                  {engagement.proposed_type !== "procurement_financial" ? (
                    <p className="muted">Confirm stays off until the file set is classified as a procurement pack.</p>
                  ) : null}
                  <label>
                    Rejection reason
                    <textarea
                      value={rejectNote}
                      placeholder="Why this proposed scope should not proceed"
                      onChange={(event) => setRejectNote(event.target.value)}
                    />
                  </label>
                </div>
              ) : role === "administrator" ? (
                <p className="muted">
                  A senior auditor confirms, rejects, or reopens this scope. Administrators do not make that decision.
                </p>
              ) : (
                <p className="muted">
                  {engagement.scope_status === "rejected"
                    ? "A senior auditor rejected this scope. Documents stay frozen until a senior reopens it."
                    : "A senior auditor confirms or rejects this scope. This role can upload and read."}
                </p>
              )}
            </div>
          )}
        </section>
      ) : null}
      <section className="panel stack">
        <h2>Documents</h2>
        {engagement?.scope_status === "rejected" || engagement?.scope_status === "confirmed" ? (
          <div className="stack">
            <p className="callout">
              {engagement.scope_status === "confirmed"
                ? "Scope is confirmed and analysis assumes this file set. Adding documents would change the evidence without updating official findings. Uploads stay closed until a senior auditor reopens scope."
                : "Uploads are closed. The file set stays as it was when the scope was rejected. A senior auditor reopens scope before anyone can add documents."}
            </p>
            {role === "senior_auditor" ? (
              <button
                className="secondary"
                type="button"
                disabled={Boolean(pending)}
                onClick={() => run("reopen", () => api(`/engagements/${params.id}/reopen-scope`, { method: "POST" }))}
              >
                {pending === "reopen" ? "Reopening…" : "Reopen scope for new documents"}
              </button>
            ) : (
              <p className="muted">Only a senior auditor can reopen scope to change the file set.</p>
            )}
          </div>
        ) : (
          <div className="upload-row">
            <label>
              Upload a PDF
              <input
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (!file) return;
                  const body = new FormData();
                  body.append("file", file);
                  void run("upload", () => api(`/engagements/${params.id}/documents`, { method: "POST", body }));
                }}
              />
            </label>
            {documents.length === 0 ? (
              <div className="sample-loader">
                <label>
                  Synthetic pack
                  <select value={packId} onChange={(event) => setPackId(event.target.value)}>
                    {(packs.length
                      ? packs
                      : [{ id: "mismatch", title: "Amount mismatch + missing approval", description: "" }]
                    ).map((pack) => (
                      <option key={pack.id} value={pack.id}>
                        {pack.title}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="secondary"
                  type="button"
                  disabled={Boolean(pending) || !engagement}
                  onClick={() =>
                    run("samples", () =>
                      api(`/engagements/${params.id}/load-samples?pack=${encodeURIComponent(packId)}`, {
                        method: "POST",
                      }),
                    )
                  }
                >
                  {pending === "samples" ? "Loading samples…" : "Load pack"}
                </button>
                {packs.find((pack) => pack.id === packId)?.description ? (
                  <p className="muted sample-hint">{packs.find((pack) => pack.id === packId)?.description}</p>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
        {error ? <p className="error">{error}</p> : null}
        <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Class</th>
              <th>Pages</th>
              <th>SHA-256</th>
            </tr>
          </thead>
          <tbody>
            {documents.length === 0 ? (
              <tr>
                <td colSpan={4}>No documents ingested.</td>
              </tr>
            ) : (
              documents.map((document) => (
                <tr key={document.id}>
                  <td>{document.filename}</td>
                  <td>{classLabel(document.document_class)}</td>
                  <td>{document.page_count}</td>
                  <td>
                    <code>{document.sha256.slice(0, 12)}</code>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>
      </section>
    </div>
  );
}
