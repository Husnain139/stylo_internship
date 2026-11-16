"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { useSession } from "@/components/session";
import { api, type AskResponse, type Citation } from "@/lib/api";

const SUGGESTIONS = [
  "What does the medical takaful policy cover?",
  "What is in the code of conduct?",
  "What is the corrective action policy?",
  "How does a provident fund loan work?",
];

type Turn = {
  role: "user" | "assistant";
  text: string;
  citations: Citation[];
};

export function AskScreen() {
  const { me, loadError, retry } = useSession();
  const questionId = useId();
  const helpId = useId();
  const errorId = useId();
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setTurns([]);
    setQuestion("");
    setError("");
  }, [me?.email]);

  async function submit(text: string) {
    const trimmed = text.trim();
    if (busy) return;
    if (!trimmed) {
      setError("Type your question first.");
      return;
    }
    setQuestion(trimmed);
    setError("");
    setBusy(true);
    const history = turns.map((turn) => ({ role: turn.role, text: turn.text }));
    try {
      const result = await api<AskResponse>("/api/ask", {
        method: "POST",
        body: JSON.stringify({ question: trimmed, history }),
      });
      setTurns((current) => [
        ...current,
        ...(trimmed ? [{ role: "user" as const, text: trimmed, citations: [] }] : []),
        { role: "assistant" as const, text: result.answer, citations: result.citations },
      ]);
      setQuestion("");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The assistant is not available right now. Try again in a moment.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!me) {
    return (
      <section className="stack auth">
        <header className="page-head">
          <h1>Ask about a policy</h1>
          <p className="lead">Sign in with the work email on your employee record. Then ask in your own words.</p>
        </header>
        <div className="actions">
          <Link className="primary" href="/sign-in">
            Sign in
          </Link>
          <Link className="secondary" href="/sign-up">
            Create a password
          </Link>
        </div>
        {loadError ? (
          <p className="form-error" role="alert">
            {loadError}{" "}
            <button type="button" onClick={() => void retry()}>
              Try again
            </button>
          </p>
        ) : null}
      </section>
    );
  }

  return (
    <section className="stack">
      <header className="page-head">
        <h1>Ask about a policy</h1>
        <p className="lead">Ask one question in your own words. The answer comes from Stylo policies.</p>
      </header>
      {turns.length > 0 ? (
        <ol className="thread">
          {turns.map((turn, index) => (
            <li key={`${turn.role}-${index}`} className={turn.role}>
              {turn.role === "user" ? (
                <p>
                  <span className="whisper">You asked</span>
                  {turn.text}
                </p>
              ) : (
                <Answer text={turn.text} citations={turn.citations} live={index === turns.length - 1} />
              )}
            </li>
          ))}
        </ol>
      ) : null}
      <form
        className="ask-form"
        aria-busy={busy}
        onSubmit={(event) => {
          event.preventDefault();
          void submit(question);
        }}
      >
        <div className="field">
          <label htmlFor={questionId}>Your question</label>
          <textarea
            id={questionId}
            name="question"
            value={question}
            rows={3}
            aria-describedby={error ? `${helpId} ${errorId}` : helpId}
            aria-invalid={error ? true : undefined}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit(question);
              }
            }}
          />
          <p id={helpId} className="help">
            One question at a time. Press Enter to ask.
          </p>
        </div>
        {error ? (
          <p id={errorId} className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Looking through the policies…" : "Ask"}
        </button>
      </form>
      {turns.length === 0 ? (
        <div className="suggestions">
          <p className="whisper">Not sure where to start? Try one of these.</p>
          <ul className="people">
            {SUGGESTIONS.map((item) => (
              <li key={item}>
                <button type="button" disabled={busy} onClick={() => void submit(item)}>
                  {item}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function Answer({ text, citations, live }: { text: string; citations: Citation[]; live: boolean }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <div>
      <p className="answer" aria-live={live ? "polite" : undefined}>
        <span className="whisper">Answer</span>
        {text}
      </p>
      {citations.length > 0 ? (
        <div className="source">
          <p>From: {citations.map((item) => item.label).join("; ")}</p>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((current) => !current)}
          >
            {open ? "Hide the policy text" : "Show the policy text"}
          </button>
          {open ? (
            <div id={panelId}>
              {citations.map((item) => (
                <div key={`${item.label}-${item.image || "text"}`}>
                  <p>{item.text}</p>
                  {item.image
                    ? item.image.split("|").map((src) => (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img key={src} src={src} alt="" />
                      ))
                    : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
