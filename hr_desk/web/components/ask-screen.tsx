"use client";

import { useEffect, useId, useState } from "react";
import { PersonChoices } from "@/components/shell";
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
  const { me, people, samples, loadError, retry, signIn } = useSession();
  const questionId = useId();
  const helpId = useId();
  const errorId = useId();
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [signingIn, setSigningIn] = useState(false);

  useEffect(() => {
    setTurns([]);
    setQuestion("");
    setError("");
  }, [me?.email]);

  async function choose(email: string) {
    setError("");
    setSigningIn(true);
    try {
      await signIn(email);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Choose a name from the list.");
    } finally {
      setSigningIn(false);
    }
  }

  async function submit(text: string) {
    const trimmed = text.trim();
    if (busy) return;
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
      <section className="stack">
        <h1>Who are you?</h1>
        <p>Practice sign-in. Company sign-in will replace this.</p>
        <PersonChoices people={people} busy={signingIn} onChoose={choose} />
        {loadError ? (
          <p className="form-error" role="alert">
            {loadError}{" "}
            <button type="button" onClick={() => void retry()}>
              Try again
            </button>
          </p>
        ) : null}
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
      </section>
    );
  }

  return (
    <section className="stack">
      <h1>Ask about a policy</h1>
      {samples ? (
        <p className="banner">These are sample policies until HR replaces them.</p>
      ) : null}
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
          Ask one question about a Stylo policy. Press Enter to ask.
        </p>
        {error ? (
          <p id={errorId} className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        {busy ? (
          <p role="status">Looking through the policies…</p>
        ) : null}
        <button className="primary" type="submit">
          Ask
        </button>
      </form>
      {turns.length === 0 ? (
        <div className="suggestions">
          <p className="whisper">Or start with one of these</p>
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
                <p key={item.label}>{item.text}</p>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
