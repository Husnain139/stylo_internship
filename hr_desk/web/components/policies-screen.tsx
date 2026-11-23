"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";
import { useSession } from "@/components/session";
import { api, type PolicyRow, type PolicyDraft, type PolicyJob } from "@/lib/api";

import { AUDIENCES } from "@/lib/policy-roles";

function toggleRole(current: string[], role: string): string[] {
  if (role === "everyone") return current.includes(role) ? [] : ["everyone"];
  const next = current.includes(role)
    ? current.filter((item) => item !== role)
    : [...current.filter((item) => item !== "everyone"), role];
  return next;
}

function RoleChecks({
  selected,
  onChange,
  labelledBy,
}: {
  selected: string[];
  onChange: (roles: string[]) => void;
  labelledBy?: string;
}) {
  return (
    <div className="checks" role="group" aria-labelledby={labelledBy}>
      {AUDIENCES.map(([value, label]) => (
        <label key={value}>
          <input
            type="checkbox"
            checked={selected.includes(value)}
            onChange={() => onChange(toggleRole(selected, value))}
          />
          {label}
        </label>
      ))}
    </div>
  );
}

export function PoliciesScreen() {
  const { me } = useSession();
  const titleId = useId();
  const audienceId = useId();
  const dateId = useId();
  const endId = useId();
  const textId = useId();
  const fileId = useId();
  const errorId = useId();
  const [policies, setPolicies] = useState<PolicyRow[] | null>(null);
  const [jobs, setJobs] = useState<PolicyJob[]>([]);
  const [drafts, setDrafts] = useState<PolicyDraft[]>([]);
  const [reviewed, setReviewed] = useState<string[]>([]);
  const [pendingRestore, setPendingRestore] = useState("");
  const [adding, setAdding] = useState(false);
  const [source, setSource] = useState<"file" | "text">("file");
  const [title, setTitle] = useState("");
  const [audiences, setAudiences] = useState<string[]>(["hr"]);
  const [startsOn, setStartsOn] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [replacing, setReplacing] = useState<PolicyRow | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [accessFor, setAccessFor] = useState<string | null>(null);
  const [accessAudiences, setAccessAudiences] = useState<string[]>(["everyone"]);
  const [accessStarts, setAccessStarts] = useState("");
  const [accessEnds, setAccessEnds] = useState("");
  const [fileKey, setFileKey] = useState(0);

  const refreshLibrary = useCallback(async () => {
    const [library, review] = await Promise.all([
      api<{ policies: PolicyRow[] }>("/api/policies"),
      api<{ drafts: PolicyDraft[] }>("/api/policy-drafts"),
    ]);
    setPolicies(library.policies);
    setDrafts(review.drafts);
  }, []);

  useEffect(() => {
    if (!me?.isAdmin) return;
    let stopped = false;
    let previous: string | null = null;
    let timer: ReturnType<typeof setTimeout>;
    async function refreshJobs() {
      try {
        const data = await api<{ jobs: PolicyJob[] }>("/api/policy-jobs");
        if (stopped) return;
        setJobs(data.jobs);
        const status = data.jobs.map((job) => `${job.id}:${job.status}`).join("|");
        if (status !== previous) {
          await refreshLibrary();
          previous = status;
        }
      } catch (caught) {
        if (!stopped) setError(caught instanceof Error ? caught.message : "Could not load the policy library.");
      } finally {
        if (!stopped) timer = setTimeout(refreshJobs, 3000);
      }
    }
    void refreshJobs();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [me?.isAdmin, refreshLibrary]);

  useEffect(() => {
    if (adding || replacing) document.getElementById(titleId)?.focus();
  }, [adding, replacing, titleId]);

  if (!me) {
    return (
      <section className="stack">
        <header className="page-head">
          <h1>Policies</h1>
          <p className="lead">Sign in to continue.</p>
        </header>
        <div className="actions">
          <Link className="primary" href="/sign-in">
            Sign in
          </Link>
        </div>
      </section>
    );
  }
  if (!me.isAdmin) {
    return (
      <section className="stack">
        <header className="page-head">
          <h1>Policies</h1>
          <p className="lead">Only an admin can open this page.</p>
        </header>
        <Link href="/">Back to Ask HR</Link>
      </section>
    );
  }

  const invalidName = error.startsWith("Give this policy");
  const invalidDate = error.startsWith("Choose the date");
  const invalidText = error.startsWith("Add the policy") || error.startsWith("We couldn't") || error.startsWith("That file");

  function resetEditor() {
    setAdding(false);
    setReplacing(null);
    setTitle("");
    setStartsOn("");
    setEndsOn("");
    setAudiences(["hr"]);
    setSource("file");
    setText("");
    setFile(null);
    setFileKey((key) => key + 1);
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    const body = new FormData();
    body.set("title", title);
    body.set("audience", audiences.join(","));
    body.set("starts_on", startsOn);
    body.set("ends_on", endsOn);
    if (source === "text") body.set("text", text);
    if (source === "file" && file) body.set("file", file);
    try {
      const result = await api<{ message: string; jobId: string }>(
        replacing ? `/api/policies/${replacing.id}` : "/api/policies",
        {
          method: "POST",
          body,
        },
      );
      setMessage(result.message);
      setJobs((items) => [{ id: result.jobId, kind: "prepare", status: "queued", title, detail: "" }, ...items]);
      resetEditor();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function updateLibrary(path: string, method: "POST" | "DELETE", draft?: PolicyDraft) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api<{ message: string; jobId?: string }>(path, {
        method,
        body: method === "POST" ? JSON.stringify({ reviewed: draft ? reviewed.includes(draft.id) : false }) : undefined,
      });
      setMessage(result.message);
      if (result.jobId) {
        const jobId = result.jobId;
        setJobs((items) => {
          const current = items.find((item) => item.id === jobId);
          const queued: PolicyJob = current
            ? { ...current, status: "queued", detail: "" }
            : { id: jobId, kind: "publish", status: "queued", title: draft?.title || "", detail: "", draftId: draft?.id };
          return [queued, ...items.filter((item) => item.id !== jobId)];
        });
      } else {
        setPendingRestore("");
        await refreshLibrary();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update the policy library.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack">
      <header className="page-head">
        <div className="section-heading">
          <h1>Policies</h1>
          {!adding && !replacing ? <button type="button" className="primary" disabled={busy} onClick={() => {
            setAdding(true);
            setError("");
            setMessage("");
          }}>Add policy</button> : null}
        </div>
      </header>
      {!adding && !replacing && error ? <p className="form-error" role="alert">{error}</p> : null}
      {!adding && !replacing && message ? <p className="success" role="status">{message}</p> : null}
      {adding || replacing ? <form className="policy-form panel" onSubmit={onSubmit}>
        <h2>{replacing ? `Replace ${replacing.title}` : "Add policy"}</h2>
        <p className="help">Review the draft before publishing.</p>
        <div className="field">
          <label htmlFor={titleId}>Policy name</label>
          <input
            id={titleId}
            value={title}
            required
            aria-invalid={invalidName || undefined}
            aria-describedby={invalidName ? errorId : undefined}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>
        <div className="field">
          <span className="field-label" id={audienceId}>Who can see it</span>
          <RoleChecks
            selected={audiences}
            labelledBy={audienceId}
            onChange={setAudiences}
          />
          {audiences.length === 0 ? <p className="help">Choose at least one role.</p> : null}
        </div>
        <div className="field-pair">
          <div className="field">
            <label htmlFor={dateId}>Starts on</label>
            <input
              id={dateId}
              type="date"
              value={startsOn}
              required
              aria-invalid={invalidDate || undefined}
              aria-describedby={invalidDate ? errorId : undefined}
              onChange={(event) => setStartsOn(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={endId}>Ends on <small>(optional)</small></label>
            <input
              id={endId}
              type="date"
              value={endsOn}
              aria-invalid={invalidDate || undefined}
              aria-describedby={invalidDate ? errorId : undefined}
              onChange={(event) => setEndsOn(event.target.value)}
            />
          </div>
        </div>
        <fieldset className="source-choice">
          <legend>Policy content</legend>
          <div className="checks">
            <label><input type="radio" name="policy-source" checked={source === "file"} onChange={() => { setSource("file"); setError(""); }} /> Upload a file</label>
            <label><input type="radio" name="policy-source" checked={source === "text"} onChange={() => { setSource("text"); setFile(null); setError(""); }} /> Paste text</label>
          </div>
        </fieldset>
        {source === "text" ? <div className="field">
          <label htmlFor={textId}>Policy text</label>
          <textarea
            id={textId}
            rows={6}
            required
            value={text}
            aria-invalid={invalidText || undefined}
            aria-describedby={invalidText ? errorId : undefined}
            onChange={(event) => setText(event.target.value)}
          />
        </div> : <div className="field">
          <label htmlFor={fileId}>Policy file</label>
          <input
            id={fileId}
            key={fileKey}
            type="file"
            required
            aria-invalid={invalidText || undefined}
            aria-describedby={invalidText ? errorId : `${fileId}-help`}
            accept=".pdf,.docx,.txt,.md,text/plain,application/pdf"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <p className="help" id={`${fileId}-help`}>PDF, Word (.docx), or text, up to 64 MB.</p>
        </div>}
        {error ? (
          <p id={errorId} className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        {message ? (
          <p role="status" className="success">
            {message}
          </p>
        ) : null}
        <div className="row-actions">
          <button className="primary" type="submit" disabled={busy || audiences.length === 0}>
            {busy ? "Submitting…" : "Prepare draft"}
          </button>
          <button type="button" disabled={busy} onClick={() => { resetEditor(); setError(""); }}>Cancel</button>
        </div>
      </form> : null}
      {jobs.some((job) => job.status !== "completed") ? (
        <section className="stack" aria-label="Policy updates">
          <h2>Policy updates</h2>
          <ul className="plain-list" aria-live="polite">
            {jobs.filter((job) => job.status !== "completed").map((job) => (
              <li key={job.id}>
                <strong>{job.title}</strong>
                <span>{job.kind === "prepare" ? "Preparing draft" : "Publishing policy"} ·
                  {" "}{({ queued: "Waiting", running: "In progress", failed: "Needs attention", completed: "Finished" })[job.status]}</span>
                {job.detail ? <span>{job.detail}</span> : null}
                {job.status === "failed" ? <button type="button" disabled={busy}
                  onClick={() => void updateLibrary(`/api/policy-jobs/${job.id}/retry`, "POST")}>Retry</button> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {drafts.length ? (
        <section className="stack" aria-label="Drafts to review">
          <h2>Drafts to review</h2>
          {drafts.map((draft) => (
            <article className="panel policy-review" key={draft.id}>
              <h3>{draft.title}</h3>
              <p>{draft.filename || "Pasted text"} · {draft.audience.split(",").map((role) => AUDIENCES.find(([key]) => key === role)?.[1] || role).join(", ")}</p>
              <p>Starts {draft.startsOn}{draft.endsOn ? `, ends ${draft.endsOn}` : ""}</p>
              {draft.hasSourceFile ? <a href={`/api/policy-drafts/${draft.id}/source`}>Download original file</a> : null}
              {draft.warnings.length ? <ul aria-label="Review notes">{draft.warnings.map((warning) =>
                <li key={warning}>{warning}</li>)}</ul> : null}
              <details>
                <summary>Review policy text</summary>
                <p className="help">
                  {draft.passages.filter((passage) => passage.type === "table").length} table sections ·{" "}
                  {new Set(draft.passages.flatMap((passage) => passage.page ? [passage.page] : [])).size} PDF pages
                </p>
                {draft.passages.map((passage, index) => (
                  <details key={index}>
                    <summary>{passage.heading} · {passage.type}{passage.page ? ` · page ${passage.page}` : ""}</summary>
                    {passage.gradeRoles.length < AUDIENCES.length - 1 ? <p>Visible to: {passage.gradeRoles.map((role) =>
                      AUDIENCES.find(([key]) => key === role)?.[1] || role).join(", ")}.</p> : null}
                    <p className="source-text">{passage.text}</p>
                  </details>
                ))}
              </details>
              <label><input type="checkbox" checked={reviewed.includes(draft.id)}
                onChange={(event) => setReviewed((items) => event.target.checked ? [...items, draft.id] : items.filter((id) => id !== draft.id))} />
                {" "}I checked the draft against the source and confirmed who can see it.
              </label>
              <div className="actions">
                <button className="primary" type="button" disabled={busy || !reviewed.includes(draft.id) || jobs.some((job) => job.draftId === draft.id && (job.status === "queued" || job.status === "running"))}
                  onClick={() => void updateLibrary(`/api/policy-drafts/${draft.id}/publish`, "POST", draft)}>Publish policy</button>
                <button type="button" disabled={busy || jobs.some((job) => job.draftId === draft.id && (job.status === "queued" || job.status === "running"))}
                  onClick={() => void updateLibrary(`/api/policy-drafts/${draft.id}`, "DELETE")}>Discard draft</button>
              </div>
            </article>
          ))}
        </section>
      ) : null}
      <h2>Policy library</h2>
      {policies === null ? (
        !error ? <p role="status">Loading policies…</p> : null
      ) : policies.length === 0 ? (
        <p className="empty-state">No policies added yet.</p>
      ) : (
        <ul className="plain-list">
          {policies.map((policy) => (
            <li key={policy.id}>
              <strong>{policy.title}</strong>
              <span className="file-name">{policy.filename || "Pasted text"}</span>
              <span className={policy.status === "Active" ? "badge ok" : "badge"}>{policy.status}</span>
              {policy.replacementStartsOn && policy.status !== "Replaced"
                ? <span>Replacement starts {policy.replacementStartsOn}.</span> : null}
              <span>
                {policy.who}. Starts {policy.starts_on}.
                {policy.ends_on ? ` Ends ${policy.ends_on}.` : ""}
              </span>
              {policy.canRollback ? (
                pendingRestore === policy.id ? <div className="actions">
                  <span>Restore the earlier version and its access settings?</span>
                  <button type="button" disabled={busy}
                    onClick={() => void updateLibrary(`/api/policies/${policy.id}/rollback`, "POST")}>Restore earlier version</button>
                  <button type="button" onClick={() => setPendingRestore("")}>Cancel</button>
                </div> : <button type="button" disabled={busy}
                  onClick={() => setPendingRestore(policy.id)}>Restore earlier version</button>
              ) : null}
              {policy.status === "Replaced" ? null : accessFor === policy.id ? (
                <div className="row-actions">
                  <span id={`who-${policy.id}`}>Who can see it</span>
                  <RoleChecks
                    selected={accessAudiences}
                    labelledBy={`who-${policy.id}`}
                    onChange={setAccessAudiences}
                  />
                  <label htmlFor={`start-${policy.id}`}>Starts on</label>
                  <input
                    id={`start-${policy.id}`}
                    type="date"
                    value={accessStarts}
                    onChange={(event) => setAccessStarts(event.target.value)}
                  />
                  <label htmlFor={`end-${policy.id}`}>Ends on <small>(optional)</small></label>
                  <input
                    id={`end-${policy.id}`}
                    type="date"
                    value={accessEnds}
                    onChange={(event) => setAccessEnds(event.target.value)}
                  />
                  {accessAudiences.length === 0 ? <p className="help">Choose at least one role.</p> : null}
                  <button
                    type="button"
                    className="primary"
                    disabled={busy || accessAudiences.length === 0}
                    onClick={() => {
                      setBusy(true);
                      setError("");
                      setMessage("");
                      api<{ message: string }>(`/api/policies/${policy.id}/access`, {
                        method: "POST",
                        body: JSON.stringify({
                          audiences: accessAudiences,
                          starts_on: accessStarts,
                          ends_on: accessEnds,
                        }),
                      })
                        .then(async (result) => {
                          setMessage(result.message);
                          setAccessFor(null);
                          const data = await api<{ policies: PolicyRow[] }>("/api/policies");
                          setPolicies(data.policies);
                        })
                        .catch((caught) =>
                          setError(caught instanceof Error ? caught.message : "Something went wrong. Try again."),
                        )
                        .finally(() => setBusy(false));
                    }}
                  >
                    Save access
                  </button>
                  <button type="button" disabled={busy} onClick={() => setAccessFor(null)}>
                    Cancel
                  </button>
                </div>
              ) : pendingDelete === policy.id ? (
                <div className="row-actions">
                  <span>Delete {policy.title}? People will no longer get answers from it.</span>
                  <button
                    type="button"
                    className="danger"
                    disabled={busy}
                    onClick={() => {
                      setBusy(true);
                      setError("");
                      setMessage("");
                      api<{ message: string }>(`/api/policies/${policy.id}`, { method: "DELETE" })
                        .then(async (result) => {
                          setMessage(result.message);
                          if (replacing?.id === policy.id) setReplacing(null);
                          setPendingDelete(null);
                          const data = await api<{ policies: PolicyRow[] }>("/api/policies");
                          setPolicies(data.policies);
                        })
                        .catch((caught) =>
                          setError(caught instanceof Error ? caught.message : "Something went wrong. Try again."),
                        )
                        .finally(() => setBusy(false));
                    }}
                  >
                    Delete this policy
                  </button>
                  <button type="button" disabled={busy} onClick={() => setPendingDelete(null)}>
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="row-actions">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setAccessFor(policy.id);
                      setAccessAudiences(policy.audience.split(","));
                      setAccessStarts(policy.starts_on);
                      setAccessEnds(policy.ends_on || "");
                      setPendingDelete(null);
                      setError("");
                      setMessage("");
                    }}
                  >
                    Change access
                  </button>
                  <button
                    type="button"
                    disabled={busy || adding || Boolean(replacing) || Boolean(policy.replacementStartsOn) || policy.status === "Scheduled"}
                    onClick={() => {
                      setReplacing(policy);
                      setSource("file");
                      setTitle(policy.title);
                      setAudiences(policy.audience.split(","));
                      setStartsOn(policy.starts_on);
                      setEndsOn(policy.ends_on || "");
                      setText("");
                      setFile(null);
                      setFileKey((key) => key + 1);
                      setPendingDelete(null);
                      setError("");
                      setMessage("");
                    }}
                  >
                    Replace
                  </button>
                  <button
                    type="button"
                    className="danger"
                    disabled={busy || Boolean(policy.replacementStartsOn)}
                    onClick={() => {
                      setPendingDelete(policy.id);
                      setError("");
                      setMessage("");
                    }}
                  >
                    Delete
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
