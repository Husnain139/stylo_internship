"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, downloadExport } from "@/lib/api";
import { useSession } from "@/lib/session";
import { formatPkr, statusLabel, type Engagement, type Finding } from "@/lib/types";

export default function AnalysisPage() {
  const params = useParams<{ id: string }>();
  const [engagement, setEngagement] = useState<Engagement | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const role = useSession()?.role;

  const reload = useCallback(async () => {
    const [nextEngagement, payload] = await Promise.all([
      api<Engagement>(`/engagements/${params.id}`),
      api<{ findings: Finding[] }>(`/engagements/${params.id}/findings`),
    ]);
    setEngagement(nextEngagement);
    setFindings(payload.findings);
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

  const hasRuns = (engagement?.analysis_run_count ?? 0) > 0;

  async function analyze() {
    setPending(true);
    setError("");
    try {
      const payload = await api<{ findings: Finding[]; analysis_run_count: number }>(
        `/engagements/${params.id}/analyze`,
        { method: "POST" },
      );
      setFindings(payload.findings);
      setEngagement((current) =>
        current ? { ...current, analysis_run_count: payload.analysis_run_count } : current,
      );
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Analysis failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="stack">
      <section className="banner">
        <strong>Processed analysis</strong>
        Rules and arithmetic produce these findings. The numbers are not taken from a model. Review on the next screen makes them official.
      </section>
      {engagement?.scope_status === "rejected" ? (
        <p className="callout">
          A senior auditor rejected this scope. Analysis stays blocked until a senior confirms it.
          {engagement.scope_rejection_note ? ` Reason: ${engagement.scope_rejection_note}` : ""}
        </p>
      ) : engagement && engagement.scope_status !== "confirmed" ? (
        <p className="callout">
          Scope is still {statusLabel(engagement.scope_status)}. Confirm it on the overview before analysis can run.
        </p>
      ) : null}
      <div className="row">
        {role === "senior_auditor" ? (
          <button type="button" disabled={pending || engagement?.scope_status !== "confirmed"} onClick={() => void analyze()}>
            {pending ? (hasRuns ? "Rerunning checks…" : "Running checks…") : hasRuns ? "Rerun analysis" : "Run analysis"}
          </button>
        ) : (
          <p className="muted">A senior auditor runs the analysis. You can read the latest findings.</p>
        )}
        {role === "senior_auditor" ? (
          <button className="secondary" type="button" onClick={() => downloadExport(params.id).catch((reason: Error) => setError(reason.message))}>
            Export JSON
          </button>
        ) : null}
      </div>
      {error ? <p className="error">{error}</p> : null}
      {findings.length === 0 ? <p className="muted">No processed findings yet.</p> : null}
      {findings.map((finding) => (
        <article key={finding.id} className="panel finding">
          <div className="finding-head">
            <h2>{finding.title}</h2>
            <div className="finding-tags">
              <span className={`pill pill-${finding.risk_band}`}>{statusLabel(finding.risk_band)} risk</span>
              <span className={`pill pill-${finding.review_status}`}>{statusLabel(finding.review_status)}</span>
            </div>
          </div>
          <p>
            <code>{finding.rule_id}</code> · {finding.narrative_status}
            {finding.delta_amount !== null ? ` · Difference ${formatPkr(finding.delta_amount)}` : ""}
          </p>
          <p>{finding.explanation}</p>
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Evidence field</th>
                <th>Value</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {finding.evidence.map((item) => (
                <tr key={item.id}>
                  <td>{item.field_name}</td>
                  <td>{item.value ?? "—"}</td>
                  <td>
                    {item.filename}
                    {item.page ? `, p.${item.page}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </article>
      ))}
    </div>
  );
}
