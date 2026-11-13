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

  useEffect(() => {
    if (me?.designation !== "hr") return;
    api<{ policies: PolicyRow[] }>("/api/policies")
      .then((data) => setPolicies(data.policies))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Something went wrong. Try again."));
  }, [me?.designation]);

  if (!me) {
    return (
      <section className="stack">
        <h1>Policies</h1>
        <p>Choose who you are to continue.</p>
        <Link href="/">Go to sign-in</Link>
      </section>
    );
  }
  if (me.designation !== "hr") {
    return (
      <section className="stack">
        <h1>Policies</h1>
        <p>This page is for HR.</p>
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
      const result = await api<{ message: string; policy: PolicyRow }>("/api/policies", {
        method: "POST",
        body,
      });
      setMessage(result.message);
      setTitle("");
      setText("");
      setFile(null);
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
      <h1>Policies</h1>
      <p>Add a policy, then choose who can ask about it.</p>
      <form className="policy-form" onSubmit={onSubmit}>
        <label htmlFor={titleId}>Policy name</label>
        <input
          id={titleId}
          value={title}
          aria-invalid={invalidName || undefined}
          aria-describedby={invalidName ? errorId : undefined}
          onChange={(event) => setTitle(event.target.value)}
        />
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
        <label htmlFor={dateId}>Starts on</label>
        <input
          id={dateId}
          type="date"
          value={startsOn}
          aria-invalid={invalidDate || undefined}
          aria-describedby={invalidDate ? errorId : undefined}
          onChange={(event) => setStartsOn(event.target.value)}
        />
        <label htmlFor={textId}>Policy text</label>
        <textarea
          id={textId}
          rows={6}
          value={text}
          aria-invalid={invalidText || undefined}
          aria-describedby={invalidText ? errorId : undefined}
          onChange={(event) => setText(event.target.value)}
        />
        <label htmlFor={fileId}>Or choose a file</label>
        <input
          id={fileId}
          type="file"
          accept=".pdf,.txt,.md,text/plain,application/pdf"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <p className="help">If you choose a file, that file is used instead of the text box.</p>
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
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Adding this policy…" : "Add this policy"}
        </button>
      </form>
      <h2>Policies people can ask about</h2>
      {policies.length === 0 ? (
        <p>No policies yet.</p>
      ) : (
        <ul className="plain-list">
          {policies.map((policy) => (
            <li key={`${policy.title}-${policy.starts_on}-${policy.audience}`}>
              <strong>{policy.title}</strong>
              <span>
                {policy.who}. Starts {policy.starts_on}.
                {policy.ends_on ? ` Ended ${policy.ends_on}.` : ""}
                {policy.sample ? " Sample." : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
