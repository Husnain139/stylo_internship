"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { useSession } from "@/components/session";
import { api, formatWhen, type QuestionRow } from "@/lib/api";

export function QuestionsScreen() {
  const { me } = useSession();
  const [rows, setRows] = useState<QuestionRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!me?.isAdmin) return;
    api<{ questions: QuestionRow[] }>("/api/questions")
      .then((data) => setRows(data.questions))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Something went wrong. Try again."));
  }, [me?.isAdmin]);

  if (!me) {
    return (
      <section className="stack">
        <header className="page-head">
          <h1>Questions people asked</h1>
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
          <h1>Questions people asked</h1>
          <p className="lead">Only an admin can open this page.</p>
        </header>
        <Link href="/">Back to Ask about a policy</Link>
      </section>
    );
  }

  return (
    <section className="stack">
      <header className="page-head">
        <h1>Questions people asked</h1>
        <p className="lead">Questions employees have asked, and what HR Desk answered.</p>
      </header>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p>Nobody has asked a question yet.</p>
      ) : (
        <ul className="plain-list">
          {rows.map((row) => (
            <QuestionItem key={row.id} row={row} />
          ))}
        </ul>
      )}
    </section>
  );
}

function QuestionItem({ row }: { row: QuestionRow }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <li>
      <p>
        <strong>{row.question || "Empty question"}</strong>
      </p>
      <p className="meta">
        {row.outcome_label} · {row.policy} · {row.asked_by} · {formatWhen(row.when)}
      </p>
      <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((value) => !value)}>
        {open ? "Hide details" : "Show details"}
      </button>
      {open ? (
        <div id={panelId}>
          <ol>
            {row.steps.map((step) => (
              <li key={step.label}>
                <strong>{step.label}.</strong> {step.detail}
              </li>
            ))}
          </ol>
          <details>
            <summary>Technical details</summary>
            <pre>{JSON.stringify(row.technical, null, 2)}</pre>
          </details>
        </div>
      ) : null}
    </li>
  );
}
