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
    if (me?.designation !== "hr") return;
    api<{ questions: QuestionRow[] }>("/api/questions")
      .then((data) => setRows(data.questions))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Something went wrong. Try again."));
  }, [me?.designation]);

  if (!me) {
    return (
      <section className="stack">
        <h1>Questions people asked</h1>
        <p>Choose who you are to continue.</p>
        <Link href="/">Go to sign-in</Link>
      </section>
    );
  }
  if (me.designation !== "hr") {
    return (
      <section className="stack">
        <h1>Questions people asked</h1>
        <p>This page is for HR.</p>
        <Link href="/">Back to Ask about a policy</Link>
      </section>
    );
  }

  return (
    <section className="stack">
      <h1>Questions people asked</h1>
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
      <p>
        {row.outcome_label}. {row.policy}. {row.asked_by}. {formatWhen(row.when)}.
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
