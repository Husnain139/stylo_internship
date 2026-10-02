"use client";

import { useEffect, useRef, useState } from "react";
import { api, type IdpException } from "@/lib/api";
import { findingCodeLabel } from "@/lib/labels";

export type ExceptionRowPayload = {
  exception: IdpException;
  columns: string[];
  row: Record<string, unknown> | null;
  row_count?: number | null;
  available: boolean;
  reason?: string | null;
};

function normalizeName(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

/** Match exception field_name(s) to cleaned columns (case/format tolerant). */
function flaggedColumns(
  columns: string[],
  fieldName: string | null | undefined,
  message: string,
): Set<string> {
  const flagged = new Set<string>();
  const byNorm = new Map(columns.map((col) => [normalizeName(col), col]));

  const candidates: string[] = [];
  if (fieldName) {
    for (const part of fieldName.split(/[,|;]/)) {
      const trimmed = part.trim();
      if (trimmed) candidates.push(trimmed);
    }
  }

  // Fallback: pull column-like tokens from the message (e.g. "Duplicate invoice_id found").
  if (!candidates.length && message) {
    for (const col of columns) {
      const norm = normalizeName(col);
      if (norm && message.toLowerCase().includes(norm.replace(/_/g, " "))) {
        candidates.push(col);
      } else if (norm && message.toLowerCase().includes(norm)) {
        candidates.push(col);
      }
    }
  }

  for (const candidate of candidates) {
    const exact = columns.find((col) => col === candidate);
    if (exact) {
      flagged.add(exact);
      continue;
    }
    const fuzzy = byNorm.get(normalizeName(candidate));
    if (fuzzy) flagged.add(fuzzy);
  }

  return flagged;
}

export function ExceptionRowInspector({
  jobId,
  exception,
  onClose,
}: {
  jobId: string;
  exception: IdpException;
  onClose: () => void;
}) {
  const rootRef = useRef<HTMLElement>(null);
  const [payload, setPayload] = useState<ExceptionRowPayload | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const node = rootRef.current;
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [exception.id]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setPayload(null);
    api<ExceptionRowPayload>(`/api/jobs/${jobId}/exceptions/${exception.id}/row`)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message || "Could not load row");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [exception.id, jobId]);

  const fieldName = payload?.exception.field_name || exception.field_name;
  const message = payload?.exception.message || exception.message;
  const columns =
    payload?.columns?.length
      ? payload.columns
      : payload?.row
        ? Object.keys(payload.row)
        : [];
  const flagged = flaggedColumns(columns, fieldName, message);

  return (
    <aside ref={rootRef} className="row-inspector" aria-label="Problem row">
      <div className="row-inspector-head">
        <div>
          <p className="kicker">Problem row</p>
          <h3>
            <span className={`pill sev-${exception.severity}`}>{exception.severity}</span>{" "}
            <span className="code-chip">{findingCodeLabel(exception.code)}</span>
            {exception.row_index != null ? (
              <span className="muted"> · row {exception.row_index}</span>
            ) : null}
          </h3>
          <p className="muted">{exception.message}</p>
        </div>
        <button type="button" className="ghost row-inspector-close" onClick={onClose}>
          Close
        </button>
      </div>

      {loading ? <p className="muted">Opening that row…</p> : null}
      {error ? <p className="error">{error}</p> : null}

      {!loading && !error && payload ? (
        payload.available && payload.row ? (
          <dl className="row-fields">
            {columns.map((col) => {
              const isFlag = flagged.has(col);
              const value = payload.row?.[col];
              return (
                <div key={col} className={isFlag ? "flagged" : undefined}>
                  <dt>
                    {col}
                    {isFlag ? <span className="flag-mark">Flagged field</span> : null}
                  </dt>
                  <dd>{value == null || value === "" ? <span className="empty-cell">blank</span> : String(value)}</dd>
                </div>
              );
            })}
          </dl>
        ) : (
          <p className="muted">{payload.reason || "This row is not available to open."}</p>
        )
      ) : null}
    </aside>
  );
}
