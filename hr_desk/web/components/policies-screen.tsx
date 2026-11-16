"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { useSession } from "@/components/session";
import { api, type PolicyRow } from "@/lib/api";

const AUDIENCES = [
  ["everyone", "Everyone"],
  ["intern", "Interns"],
  ["employee", "Employees"],
  ["manager", "Managers"],
  ["hr", "HR"],
  ["executive", "Executives"],
] as const;

export function PoliciesScreen() {
  const { me } = useSession();
  const titleId = useId();
  const audienceId = useId();
  const dateId = useId();
  const textId = useId();
  const fileId = useId();
  const errorId = useId();
  const [policies, setPolicies] = useState<PolicyRow[]>([]);
  const [title, setTitle] = useState("");
  const [audience, setAudience] = useState("everyone");
  const [startsOn, setStartsOn] = useState("2026-01-01");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [replacing, setReplacing] = useState<PolicyRow | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [fileKey, setFileKey] = useState(0);

  useEffect(() => {
    if (!me?.isAdmin) return;
    api<{ policies: PolicyRow[] }>("/api/policies")
      .then((data) => setPolicies(data.policies))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Something went wrong. Try again."));
  }, [me?.isAdmin]);

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
        <Link href="/">Back to Ask about a policy</Link>
      </section>
    );
  }

  const invalidName = error.startsWith("Give this policy");
  const invalidAudience = error.startsWith("Choose who can see");
  const invalidDate = error.startsWith("Choose the date");
  const invalidText = error.startsWith("Add the policy") || error.startsWith("We couldn't") || error.startsWith("That file");

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    const body = new FormData();
    body.set("title", title);
    body.set("audience", audience);
    body.set("starts_on", startsOn);
    body.set("text", text);
    if (file) body.set("file", file);
    try {
      const result = await api<{ message: string; policy: PolicyRow }>(
        replacing ? `/api/policies/${replacing.id}` : "/api/policies",
        {
          method: "POST",
          body,
        },
      );
      setMessage(result.message);
      setTitle("");
      setText("");
      setFile(null);
      setFileKey((key) => key + 1);
      setReplacing(null);
      const data = await api<{ policies: PolicyRow[] }>("/api/policies");
      setPolicies(data.policies);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack">
      <header className="page-head">
        <h1>Policies</h1>
        <p className="lead">Add a company policy, replace one that is already listed, or delete it.</p>
      </header>
      <form className="policy-form panel" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor={titleId}>Policy name</label>
          <input
            id={titleId}
            value={title}
            aria-invalid={invalidName || undefined}
            aria-describedby={invalidName ? errorId : undefined}
            onChange={(event) => setTitle(event.target.value)}
          />
          <p className="help">A short name employees will recognize, such as Travel Policy.</p>
        </div>
        <div className="field">
          <label htmlFor={audienceId}>Who can see it</label>
          <select
            id={audienceId}
            value={audience}
            aria-invalid={invalidAudience || undefined}
            aria-describedby={invalidAudience ? errorId : undefined}
            onChange={(event) => setAudience(event.target.value)}
          >
            {AUDIENCES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <p className="help">Everyone means any person who is signed in.</p>
        </div>
        <div className="field">
          <label htmlFor={dateId}>Starts on</label>
          <input
            id={dateId}
            type="date"
            value={startsOn}
            aria-invalid={invalidDate || undefined}
            aria-describedby={invalidDate ? errorId : undefined}
            onChange={(event) => setStartsOn(event.target.value)}
          />
          <p className="help">The day this policy starts to apply.</p>
        </div>
        <div className="field">
          <label htmlFor={textId}>Policy text</label>
          <textarea
            id={textId}
            rows={6}
            value={text}
            aria-invalid={invalidText || undefined}
            aria-describedby={invalidText ? errorId : undefined}
            onChange={(event) => setText(event.target.value)}
          />
          <p className="help">Paste the policy here, or leave this empty and upload a file below.</p>
        </div>
        <div className="field">
          <label htmlFor={fileId}>Or choose a file</label>
          <input
            id={fileId}
            key={fileKey}
            type="file"
            accept=".pdf,.docx,.txt,.md,text/plain,application/pdf"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <p className="help">A PDF, Word, or text file. A file is used instead of the box above.</p>
          {replacing ? (
            <p className="help">
              Replacing {replacing.title}. The current passages are removed when this is saved.
            </p>
          ) : null}
        </div>
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
          <button className="primary" type="submit" disabled={busy}>
            {busy
              ? replacing
                ? "Replacing this policy…"
                : "Adding this policy…"
              : replacing
                ? "Replace this policy"
                : "Add this policy"}
          </button>
          {replacing ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setReplacing(null);
                setTitle("");
                setText("");
                setFile(null);
                setFileKey((key) => key + 1);
                setError("");
              }}
            >
              Cancel
            </button>
          ) : null}
        </div>
      </form>
      <h2>Policies people can ask about</h2>
      {policies.length === 0 ? (
        <p>No policies have been added yet.</p>
      ) : (
        <ul className="plain-list">
          {policies.map((policy) => (
            <li key={policy.id}>
              <strong>{policy.title}</strong>
              <span className="file-name">{policy.filename || "Pasted text"}</span>
              <span>
                {policy.who}. Starts {policy.starts_on}.
                {policy.ends_on ? ` Ended ${policy.ends_on}.` : ""}
              </span>
              {pendingDelete === policy.id ? (
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
                      setReplacing(policy);
                      setTitle(policy.title);
                      setAudience(policy.audience);
                      setStartsOn(policy.starts_on);
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
                    disabled={busy}
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
