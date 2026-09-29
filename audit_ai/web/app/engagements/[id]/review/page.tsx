"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { formatEngagementDate, formatPkr, statusLabel, type Finding } from "@/lib/types";

export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const [findings, setFindings] = useState<Finding[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [revising, setRevising] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [pending, setPending] = useState("");
  const senior = useSession()?.role === "senior_auditor";

  const reload = useCallback(async () => {
    const payload = await api<{ findings: Finding[] }>(`/engagements/${params.id}/findings`);
    setFindings(payload.findings);
  }, [params.id]);

  useEffect(() => {
    let cancelled = false;
    api<{ findings: Finding[] }>(`/engagements/${params.id}/findings`)
      .then((payload) => {
        if (!cancelled) setFindings(payload.findings);
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  async function review(findingId: string, action: "approve" | "correct" | "reject") {
    setPending(findingId + action);
    setError("");
    try {
      await api(`/findings/${findingId}/review`, {
        method: "POST",
        body: JSON.stringify({ action, note: notes[findingId] || null }),
      });
      setRevising((current) => ({ ...current, [findingId]: false }));
      setNotes((current) => ({ ...current, [findingId]: "" }));
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Review failed");
    } finally {
      setPending("");
    }
  }

  return (
    <div className="stack">
      <section className="banner">
        <strong>Human review</strong>
        Approving a finding records an exception that needs investigation. It does not declare wrongdoing. After a
        decision is recorded, the form locks; revise only if the conclusion must change.
      </section>
      {!senior ? <p className="muted">Review actions are limited to senior auditors. You can read the current status.</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {findings.length === 0 ? <p className="muted">Run analysis before there is anything to review.</p> : null}
      {findings.map((finding) => {
        const decided = finding.review_status !== "open";
        const editing = !decided || revising[finding.id];
        return (
          <article key={finding.id} className="panel stack">
            <div className="finding-head">
              <h2>{finding.title}</h2>
              <div className="finding-tags">
                <span className={`pill pill-${finding.risk_band}`}>{statusLabel(finding.risk_band)} risk</span>
                <span className={`pill pill-${finding.review_status}`}>{statusLabel(finding.review_status)}</span>
              </div>
            </div>
            <p>
              {finding.narrative_status}
              {finding.delta_amount !== null ? ` · ${formatPkr(finding.delta_amount)}` : ""}
            </p>
            <p>{finding.explanation}</p>
            {decided && !editing ? (
              <div className="decision-record">
                <p className="scope-label">Recorded decision</p>
                <p className="scope-body">
                  {statusLabel(finding.review_status)} by {finding.reviewed_by}
                  {finding.reviewed_at ? ` on ${formatEngagementDate(finding.reviewed_at)}` : ""}
                </p>
                {finding.review_note ? <p className="scope-body">Note: {finding.review_note}</p> : null}
                {senior ? (
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => {
                      setRevising((current) => ({ ...current, [finding.id]: true }));
                      setNotes((current) => ({ ...current, [finding.id]: finding.review_note ?? "" }));
                    }}
                  >
                    Revise decision
                  </button>
                ) : null}
              </div>
            ) : null}
            {senior && editing ? (
              <>
                {decided ? (
                  <p className="callout">
                    Revising replaces the previous decision on this finding. The earlier action stays in the append-only
                    audit log.
                  </p>
                ) : null}
                <label>
                  Note
                  <textarea
                    value={notes[finding.id] ?? ""}
                    placeholder={finding.review_status === "open" ? "Optional for approve or reject; required to correct" : undefined}
                    onChange={(event) => setNotes((current) => ({ ...current, [finding.id]: event.target.value }))}
                  />
                </label>
                <div className="row">
                  <button type="button" disabled={Boolean(pending)} onClick={() => void review(finding.id, "approve")}>
                    Approve
                  </button>
                  <button
                    className="secondary"
                    type="button"
                    disabled={Boolean(pending)}
                    onClick={() => void review(finding.id, "correct")}
                  >
                    Correct
                  </button>
                  <button
                    className="secondary"
                    type="button"
                    disabled={Boolean(pending)}
                    onClick={() => void review(finding.id, "reject")}
                  >
                    Reject
                  </button>
                  {decided ? (
                    <button
                      className="secondary"
                      type="button"
                      disabled={Boolean(pending)}
                      onClick={() => {
                        setRevising((current) => ({ ...current, [finding.id]: false }));
                        setNotes((current) => ({ ...current, [finding.id]: "" }));
                      }}
                    >
                      Cancel
                    </button>
                  ) : null}
                </div>
              </>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
