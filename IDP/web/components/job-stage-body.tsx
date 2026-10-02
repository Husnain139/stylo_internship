"use client";

import { useEffect, useState } from "react";
import { ExceptionRowInspector } from "@/components/exception-row-inspector";
import { SoftLink, jobStagePath } from "@/components/job-stage-nav";
import { useJob } from "@/components/job-provider";
import { api, downloadExport, type IdpException, type StageId } from "@/lib/api";
import {
  auditEventLabel,
  exportBlockedReason,
  findingCodeLabel,
  statusLabel,
  valueKindLabel,
} from "@/lib/labels";

type CleanOpts = {
  drop_blank_rows: boolean;
  drop_blank_keys: boolean;
  dedupe_keys: boolean;
  drop_exact_duplicates: boolean;
  rename_erp: boolean;
  trim_whitespace: boolean;
  nullify_placeholders: boolean;
  normalize_numbers: boolean;
  standardize_dates: boolean;
  lowercase_emails: boolean;
  uppercase_ids: boolean;
};

const DEFAULT_CLEAN_OPTS: CleanOpts = {
  drop_blank_rows: true,
  drop_blank_keys: true,
  dedupe_keys: true,
  drop_exact_duplicates: false,
  rename_erp: true,
  trim_whitespace: true,
  nullify_placeholders: true,
  normalize_numbers: true,
  standardize_dates: true,
  lowercase_emails: true,
  uppercase_ids: false,
};

const CLEAN_CHOICES: { key: keyof CleanOpts; label: string; hint: string }[] = [
  { key: "drop_blank_rows", label: "Remove blank rows", hint: "Drop rows where every cell is empty" },
  { key: "drop_blank_keys", label: "Remove rows missing invoice / key", hint: "Drop rows with blank invoice or key values" },
  { key: "dedupe_keys", label: "Remove duplicate invoices / keys", hint: "Keep the first row for each invoice or key; drop later duplicates" },
  { key: "drop_exact_duplicates", label: "Remove identical rows", hint: "Drop rows that match on every field" },
  { key: "rename_erp", label: "Use standard field names", hint: "Align column names to the usual finance names" },
  { key: "trim_whitespace", label: "Trim extra spaces", hint: "Clean leading/trailing and repeated spaces" },
  { key: "nullify_placeholders", label: "Treat N/A as blank", hint: "Turn N/A, null, -, none into empty cells" },
  { key: "normalize_numbers", label: "Clean amounts", hint: "Strip currency symbols and thousand separators" },
  { key: "standardize_dates", label: "Standardize dates", hint: "Convert common date forms to a consistent format" },
  { key: "lowercase_emails", label: "Normalize emails", hint: "Lowercase email addresses" },
  { key: "uppercase_ids", label: "Uppercase IDs / codes", hint: "Uppercase invoice numbers and similar codes" },
];

const AUTO_INCLUDED = CLEAN_CHOICES.filter((c) => DEFAULT_CLEAN_OPTS[c.key]).map((c) => c.label);
const AUTO_EXCLUDED = CLEAN_CHOICES.filter((c) => !DEFAULT_CLEAN_OPTS[c.key]).map((c) => c.label);

export function JobStageBody({ viewStage }: { viewStage: StageId }) {
  const { detail, pending, notes, setNotes, setError, run, decide } = useJob();
  const [selectedException, setSelectedException] = useState<IdpException | null>(null);
  const [cleanOpts, setCleanOpts] = useState<CleanOpts | null>(null);

  useEffect(() => {
    setSelectedException(null);
    setCleanOpts(null);
  }, [viewStage, detail?.id]);

  if (!detail) return null;

  const pendingExceptions = detail.exceptions.filter((e) => e.status === "pending");
  const previewRows = (detail.cleaned?.rows || []).slice(0, 8);
  const columns = detail.cleaned?.columns || [];
  const checklist = (detail.validation?.review_checklist || {}) as {
    focus?: string[];
    likely_keys?: string[];
    erp_risks?: string[];
    summary?: string;
  };
  const raw = detail.raw_preview || {};
  const jobId = detail.id;

  if (viewStage === "upload") {
    return (
      <section className="panel stage-detail">
        <header className="stage-detail-head">
          <h2>Receive</h2>
          <p className="muted">Your file is on file for this review.</p>
        </header>
        <dl className="meta-list">
          <div>
            <dt>File name</dt>
            <dd>{detail.filename}</dd>
          </div>
          <div>
            <dt>Document type</dt>
            <dd>{detail.source_kind || String(raw.kind || "—")}</dd>
          </div>
          <div>
            <dt>Rows found</dt>
            <dd>{String(raw.row_count ?? "—")}</dd>
          </div>
        </dl>
        {Array.isArray(raw.columns) && (raw.columns as string[]).length ? (
          <div className="field-block">
            <p className="field-label">Fields found in the file</p>
            <div className="chip-row">
              {(raw.columns as string[]).map((col) => (
                <code key={col}>{col}</code>
              ))}
            </div>
          </div>
        ) : null}
      </section>
    );
  }

  if (viewStage === "analyze") {
    const important = (
      (detail.analysis?.important_data as { label?: string; value?: string; why?: string }[] | undefined) || []
    ).filter((item) => item && item.label);

    return (
      <section className="panel stage-detail">
        <header className="stage-detail-head">
          <h2>Document overview</h2>
          <p className="muted">Key facts noticed in the file before you prepare it.</p>
        </header>

        <div className="important-data">
          <h3>Important data</h3>
          <p className="muted">What to notice first — totals, parties, dates, and identifiers.</p>
          {important.length ? (
            <dl className="important-grid">
              {important.map((item, idx) => (
                <div key={`${item.label}-${idx}`}>
                  <dt>{item.label}</dt>
                  <dd>
                    <strong>{item.value || "—"}</strong>
                    {item.why ? <small>{item.why}</small> : null}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="muted">No highlights were found for this file.</p>
          )}
        </div>

        <dl className="meta-list">
          <div>
            <dt>Document type</dt>
            <dd>
              {String(
                (detail.analysis as { document_type_label?: string } | undefined)?.document_type_label ||
                  detail.analysis?.document_type ||
                  "—",
              )}
            </dd>
          </div>
          <div>
            <dt>Notes</dt>
            <dd>{String(detail.analysis?.notes || "—")}</dd>
          </div>
        </dl>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Field in file</th>
                <th>Kind of value</th>
              </tr>
            </thead>
            <tbody>
              {((detail.analysis?.columns as { name?: string; erp_name?: string; dtype?: string }[]) || []).map(
                (col, idx) => (
                  <tr key={`${col.name}-${idx}`}>
                    <td>{col.name}</td>
                    <td>{valueKindLabel(col.dtype)}</td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      </section>
    );
  }

  if (viewStage === "clean") {
    const applied = detail.cleaned?.options;
    const awaiting = detail.status === "awaiting_clean" || !detail.cleaned?.row_count;
    const canClean = detail.status !== "exported" && detail.status !== "failed";
    const opts: CleanOpts = {
      drop_blank_rows: cleanOpts?.drop_blank_rows ?? applied?.drop_blank_rows ?? DEFAULT_CLEAN_OPTS.drop_blank_rows,
      drop_blank_keys: cleanOpts?.drop_blank_keys ?? applied?.drop_blank_keys ?? DEFAULT_CLEAN_OPTS.drop_blank_keys,
      dedupe_keys: cleanOpts?.dedupe_keys ?? applied?.dedupe_keys ?? DEFAULT_CLEAN_OPTS.dedupe_keys,
      drop_exact_duplicates:
        cleanOpts?.drop_exact_duplicates ??
        applied?.drop_exact_duplicates ??
        DEFAULT_CLEAN_OPTS.drop_exact_duplicates,
      rename_erp: cleanOpts?.rename_erp ?? applied?.rename_erp ?? DEFAULT_CLEAN_OPTS.rename_erp,
      trim_whitespace: cleanOpts?.trim_whitespace ?? applied?.trim_whitespace ?? DEFAULT_CLEAN_OPTS.trim_whitespace,
      nullify_placeholders:
        cleanOpts?.nullify_placeholders ??
        applied?.nullify_placeholders ??
        DEFAULT_CLEAN_OPTS.nullify_placeholders,
      normalize_numbers:
        cleanOpts?.normalize_numbers ?? applied?.normalize_numbers ?? DEFAULT_CLEAN_OPTS.normalize_numbers,
      standardize_dates:
        cleanOpts?.standardize_dates ?? applied?.standardize_dates ?? DEFAULT_CLEAN_OPTS.standardize_dates,
      lowercase_emails:
        cleanOpts?.lowercase_emails ?? applied?.lowercase_emails ?? DEFAULT_CLEAN_OPTS.lowercase_emails,
      uppercase_ids: cleanOpts?.uppercase_ids ?? applied?.uppercase_ids ?? DEFAULT_CLEAN_OPTS.uppercase_ids,
    };

    return (
      <section className="panel stage-detail">
        <header className="stage-detail-head">
          <h2>Prepare the file</h2>
          <p className="muted">
            {awaiting
              ? "Choose what blanks and duplicates to fix, then apply your choices — or use the recommended fix."
              : "Change your choices and apply again if needed, or use the recommended fix."}
          </p>
        </header>

        {canClean ? (
          <fieldset className="clean-options">
            <legend>What to fix</legend>
            <div className="clean-option-toolbar">
              <button
                type="button"
                className="ghost linkish"
                disabled={Boolean(pending)}
                onClick={() =>
                  setCleanOpts(
                    Object.fromEntries(CLEAN_CHOICES.map((c) => [c.key, true])) as CleanOpts,
                  )
                }
              >
                Select all
              </button>
              <button
                type="button"
                className="ghost linkish"
                disabled={Boolean(pending)}
                onClick={() =>
                  setCleanOpts(
                    Object.fromEntries(CLEAN_CHOICES.map((c) => [c.key, false])) as CleanOpts,
                  )
                }
              >
                Unselect all
              </button>
              <button
                type="button"
                className="ghost linkish"
                disabled={Boolean(pending)}
                onClick={() => setCleanOpts({ ...DEFAULT_CLEAN_OPTS })}
              >
                Recommended
              </button>
            </div>
            <div className="clean-option-scroll">
              <div className="clean-option-grid">
                {CLEAN_CHOICES.map((choice) => (
                  <label key={choice.key} className="clean-option">
                    <input
                      type="checkbox"
                      checked={opts[choice.key]}
                      disabled={Boolean(pending)}
                      onChange={(event) =>
                        setCleanOpts({
                          ...opts,
                          [choice.key]: event.target.checked,
                        })
                      }
                    />
                    <span>
                      <strong>{choice.label}</strong>
                      <small>{choice.hint}</small>
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <div className="clean-actions-block">
              <div className="actions clean-actions sticky-actions">
                <button
                  type="button"
                  disabled={Boolean(pending)}
                  title="Runs only the options you checked above."
                  onClick={() =>
                    void run("clean-apply", () =>
                      api(`/api/jobs/${jobId}/clean`, {
                        method: "POST",
                        body: JSON.stringify({ mode: "custom", ...opts }),
                      }),
                    )
                  }
                >
                  {pending === "clean-apply" ? "Applying…" : "Apply my choices"}
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={Boolean(pending)}
                  title={`Ignores checkboxes. Recommended includes: ${AUTO_INCLUDED.join(", ")}. Leaves off: ${AUTO_EXCLUDED.join(", ")}.`}
                  onClick={() =>
                    void run("clean-auto", () =>
                      api(`/api/jobs/${jobId}/clean`, {
                        method: "POST",
                        body: JSON.stringify({ mode: "auto" }),
                      }),
                    )
                  }
                >
                  {pending === "clean-auto" ? "Fixing…" : "Recommended fix"}
                </button>
              </div>
              <div className="clean-auto-hint muted">
                <p>
                  <strong>Apply my choices</strong> runs only what you checked.
                </p>
                <p>
                  <strong>Recommended fix</strong> ignores checkboxes and uses the usual safe set for blanks,
                  duplicates, amounts, and dates. It leaves off identical-row removal and uppercasing IDs
                  unless you turn those on yourself.
                </p>
              </div>
            </div>
          </fieldset>
        ) : null}

        {awaiting ? (
          <ul className="clean-checklist">
            <li>Tick the blanks and duplicates you want fixed, then Apply my choices</li>
            <li>Or use Recommended fix for the usual safe set</li>
            <li>Recommended leaves “identical rows” and “uppercase IDs” off</li>
          </ul>
        ) : null}

        <dl className="meta-list">
          <div>
            <dt>Rows before</dt>
            <dd>{detail.cleaned?.stats?.input_rows ?? "—"}</dd>
          </div>
          <div>
            <dt>Blank rows removed</dt>
            <dd>{detail.cleaned?.stats?.blank_rows_removed ?? "—"}</dd>
          </div>
          <div>
            <dt>Missing-key rows removed</dt>
            <dd>{detail.cleaned?.stats?.blank_key_rows_removed ?? "—"}</dd>
          </div>
          <div>
            <dt>Duplicates removed</dt>
            <dd>{detail.cleaned?.stats?.duplicates_removed ?? "—"}</dd>
          </div>
          <div>
            <dt>Identical rows removed</dt>
            <dd>{detail.cleaned?.stats?.exact_duplicates_removed ?? "—"}</dd>
          </div>
          <div>
            <dt>Rows kept</dt>
            <dd>{detail.cleaned?.row_count ?? "—"}</dd>
          </div>
        </dl>
        <div className="field-block">
          <p className="field-label">
            {previewRows.length
              ? `Preview (first ${previewRows.length} rows after fixes)`
              : awaiting
                ? "No preview yet — apply your choices or use Recommended fix"
                : "Preview"}
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {columns.length ? (
                    columns.map((col) => <th key={col}>{col}</th>)
                  ) : (
                    <th>—</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {previewRows.length === 0 ? (
                  <tr>
                    <td colSpan={Math.max(columns.length, 1)}>
                      {awaiting ? "Waiting for your prepare choices." : "No rows left after fixes."}
                    </td>
                  </tr>
                ) : (
                  previewRows.map((row, idx) => (
                    <tr key={idx}>
                      {columns.map((col) => (
                        <td key={col}>{String(row[col] ?? "")}</td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    );
  }

  if (viewStage === "validate") {
    const findingCount = detail.validation?.exception_count ?? detail.exceptions.length;
    return (
      <section className="panel stage-detail">
        <header className="stage-detail-head">
          <h2>Findings</h2>
          <p className="muted">
            {findingCount === 0
              ? "No inconsistencies found — you can continue."
              : `${findingCount} inconsistenc${findingCount === 1 ? "y" : "ies"} to review (blanks, duplicates, bad amounts or dates, and similar).`}
          </p>
        </header>
        <dl className="meta-list">
          <div>
            <dt>Status</dt>
            <dd>{detail.validation?.ok ? "No issues needing review" : "Issues need your review"}</dd>
          </div>
          <div>
            <dt>Issues found</dt>
            <dd>{findingCount}</dd>
          </div>
          <div>
            <dt>Rows checked</dt>
            <dd>
              {String((detail.validation?.summary as { rows_checked?: number } | undefined)?.rows_checked ?? "—")}
            </dd>
          </div>
          <div>
            <dt>Key fields</dt>
            <dd>
              {((detail.validation?.summary as { key_columns?: string[] } | undefined)?.key_columns || []).join(
                ", ",
              ) || "—"}
            </dd>
          </div>
        </dl>
        <div className="table-wrap">
          <table className="exception-table">
            <thead>
              <tr>
                <th>How serious</th>
                <th>Type</th>
                <th>What we found</th>
                <th>Row</th>
                <th>Field</th>
              </tr>
            </thead>
            <tbody>
              {detail.exceptions.length === 0 ? (
                <tr>
                  <td colSpan={5}>No findings — continue to Decide or Download.</td>
                </tr>
              ) : (
                detail.exceptions.map((item) => {
                  const active = selectedException?.id === item.id;
                  return (
                    <tr
                      key={item.id}
                      className={`exception-row${active ? " active" : ""}`}
                      tabIndex={0}
                      aria-selected={active}
                      onClick={() => setSelectedException(item)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedException(item);
                        }
                      }}
                    >
                      <td className="sev-cell">
                        <span className={`pill sev-${item.severity}`}>{item.severity}</span>
                        <span className="open-row-hint">{active ? "Looking at row" : "Open finding"}</span>
                      </td>
                      <td>
                        <span className="code-chip">{findingCodeLabel(item.code)}</span>
                      </td>
                      <td>{item.message}</td>
                      <td>{item.row_index ?? "—"}</td>
                      <td>{item.field_name || "—"}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        {selectedException ? (
          <ExceptionRowInspector
            jobId={jobId}
            exception={selectedException}
            onClose={() => setSelectedException(null)}
          />
        ) : (
          <p className="muted tip-line">Select a finding to open that problem row.</p>
        )}
      </section>
    );
  }

  if (viewStage === "approve") {
    return (
      <section className="panel">
        <div className="panel-head">
          <h2>Review &amp; decide</h2>
          <div className="actions">
            {pendingExceptions.length ? (
              <button
                type="button"
                disabled={Boolean(pending)}
                onClick={() =>
                  void run("approve-all", () =>
                    api(`/api/jobs/${jobId}/exceptions/approve-all`, {
                      method: "POST",
                      body: JSON.stringify({ note: "Bulk approved" }),
                    }),
                  )
                }
              >
                Accept all needing review
              </button>
            ) : null}
          </div>
        </div>
        <p className="muted">
          Your decision is required before download. If something should be corrected, write it in the note — those
          notes (and the checklist below) can be applied into the finished file.
        </p>

        {checklist.focus?.length || checklist.likely_keys?.length || checklist.summary ? (
          <div className="checklist">
            <h3>Things to double-check</h3>
            <p className="muted">Guidance only — you still decide each finding.</p>
            {checklist.summary ? <p>{checklist.summary}</p> : null}
            {checklist.likely_keys?.length ? (
              <p className="muted">
                Likely identity fields:{" "}
                {checklist.likely_keys.map((key, index) => (
                  <span key={key}>
                    {index > 0 ? " · " : null}
                    <code>{key}</code>
                  </span>
                ))}
              </p>
            ) : null}
            {checklist.focus?.length ? (
              <ul>
                {checklist.focus.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
            {checklist.erp_risks?.length ? (
              <>
                <p className="muted">Import risks if ignored</p>
                <ul>
                  {checklist.erp_risks.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        ) : null}

        <div className="table-wrap">
          <table className="exception-table">
            <thead>
              <tr>
                <th>How serious</th>
                <th>Type</th>
                <th>What we found</th>
                <th>Row</th>
                <th>Field</th>
                <th>Status</th>
                <th>Your decision</th>
              </tr>
            </thead>
            <tbody>
              {detail.exceptions.length === 0 ? (
                <tr>
                  <td colSpan={7}>No findings — continue to Download.</td>
                </tr>
              ) : (
                detail.exceptions.map((item) => {
                  const active = selectedException?.id === item.id;
                  return (
                    <tr
                      key={item.id}
                      className={`exception-row${active ? " active" : ""}`}
                      tabIndex={0}
                      aria-selected={active}
                      onClick={() => setSelectedException(item)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedException(item);
                        }
                      }}
                    >
                      <td className="sev-cell">
                        <span className={`pill sev-${item.severity}`}>{item.severity}</span>
                        <span className="open-row-hint">{active ? "Looking at row" : "Open finding"}</span>
                      </td>
                      <td>
                        <span className="code-chip">{findingCodeLabel(item.code)}</span>
                      </td>
                      <td>{item.message}</td>
                      <td>{item.row_index ?? "—"}</td>
                      <td>{item.field_name || "—"}</td>
                      <td>
                        <span className="pill status-quiet">{statusLabel(item.status)}</span>
                      </td>
                      <td
                        onClick={(event) => event.stopPropagation()}
                        onKeyDown={(event) => event.stopPropagation()}
                      >
                        {item.status === "pending" ? (
                          <div className="decide">
                            <input
                              placeholder="What to fix (optional)"
                              value={notes[item.id] || ""}
                              onChange={(event) =>
                                setNotes((prev) => ({ ...prev, [item.id]: event.target.value }))
                              }
                            />
                            <button type="button" disabled={Boolean(pending)} onClick={() => void decide(item, "approve")}>
                              Accept
                            </button>
                            <button
                              type="button"
                              className="danger"
                              disabled={Boolean(pending)}
                              onClick={() => void decide(item, "reject")}
                            >
                              Send back
                            </button>
                          </div>
                        ) : (
                          <span className="muted">{item.decision_note || statusLabel(item.status)}</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        {selectedException ? (
          <ExceptionRowInspector
            jobId={jobId}
            exception={selectedException}
            onClose={() => setSelectedException(null)}
          />
        ) : detail.exceptions.length ? (
          <p className="muted tip-line">Select a finding to open that problem row.</p>
        ) : null}
      </section>
    );
  }

  const blocked = exportBlockedReason(detail);
  const canGenerate =
    !pending &&
    detail.status !== "awaiting_approval" &&
    detail.status !== "blocked_rejections" &&
    detail.status !== "awaiting_clean" &&
    detail.status !== "cleaning";
  const remediations = detail.cleaned?.remediations;
  const canDownloadResult =
    Boolean(detail.cleaned?.result_path) || detail.status === "exported" || detail.status === "ready_to_export";

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2>Finish &amp; download</h2>
          <div className="actions">
            <button
              type="button"
              disabled={!canGenerate}
              onClick={() => void run("export", () => api(`/api/jobs/${jobId}/export`, { method: "POST" }))}
            >
              {pending === "export" ? "Preparing…" : "Prepare download pack"}
            </button>
            <button
              type="button"
              className="ghost"
              disabled={!canDownloadResult}
              onClick={() => void downloadExport(detail.id, "result").catch((e: Error) => setError(e.message))}
            >
              Download finished file
            </button>
            <button
              type="button"
              className="ghost"
              disabled={detail.status !== "exported"}
              onClick={() => void downloadExport(detail.id, "csv").catch((e: Error) => setError(e.message))}
            >
              Download CSV
            </button>
            <button
              type="button"
              className="ghost"
              disabled={detail.status !== "exported" || !(detail.export_formats || []).includes("xlsx")}
              onClick={() => void downloadExport(detail.id, "xlsx").catch((e: Error) => setError(e.message))}
            >
              Download spreadsheet
            </button>
          </div>
        </div>
        {blocked ? (
          <div className="export-blocked">
            <p>{blocked}</p>
            {(detail.status === "awaiting_approval" || detail.status === "blocked_rejections") && (
              <SoftLink className="button-link ghost" href={jobStagePath(jobId, "approve")} stage="approve">
                Go to Review &amp; decide →
              </SoftLink>
            )}
          </div>
        ) : (
          <p className="muted">
            After you accept findings, fixes from your notes are built into the finished file. Prepare the download
            pack when you are ready.
          </p>
        )}
        {detail.xlsx_skipped_reason ? (
          <p className="muted">Spreadsheet download may be unavailable for very large files — use CSV.</p>
        ) : null}
      </section>

      {remediations ? (
        <section className="panel" style={{ marginTop: "1rem" }}>
          <h2>Fixes applied from your notes</h2>
          <p className="muted">{remediations.summary || "Note and checklist steps were reviewed."}</p>
          <dl className="meta-list">
            <div>
              <dt>Changes applied</dt>
              <dd>{remediations.changes_applied ?? 0}</dd>
            </div>
            <div>
              <dt>Rows removed</dt>
              <dd>{remediations.rows_dropped ?? 0}</dd>
            </div>
          </dl>
          {remediations.steps_considered?.length ? (
            <div className="field-block">
              <p className="field-label">Checklist items considered</p>
              <ul className="clean-checklist">
                {remediations.steps_considered.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {remediations.applied?.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Change</th>
                    <th>Row</th>
                    <th>Field</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {remediations.applied.map((item, idx) => (
                    <tr key={`${item.field}-${idx}`}>
                      <td>{item.status || "—"}</td>
                      <td>{item.action || "—"}</td>
                      <td>{item.row_index ?? "—"}</td>
                      <td>{item.field || "—"}</td>
                      <td>{item.reason || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">No field changes were needed from the notes.</p>
          )}
        </section>
      ) : null}

      <section className="panel" style={{ marginTop: "1rem" }}>
        <h2>Activity record</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>What happened</th>
                <th>Who</th>
              </tr>
            </thead>
            <tbody>
              {detail.audit_trail.map((event) => (
                <tr key={event.id}>
                  <td>{new Date(event.created_at).toLocaleString()}</td>
                  <td>{auditEventLabel(event.event)}</td>
                  <td>{event.actor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
