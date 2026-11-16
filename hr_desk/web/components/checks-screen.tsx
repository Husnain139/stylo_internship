"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSession } from "@/components/session";
import { api, formatWhen, type ChecksResponse } from "@/lib/api";

export function ChecksScreen() {
  const { me } = useSession();
  const [report, setReport] = useState<ChecksResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!me?.isAdmin) return;
    api<ChecksResponse>("/api/checks")
      .then(setReport)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Something went wrong. Try again."));
  }, [me?.isAdmin]);

  if (!me) {
    return (
      <section className="stack">
        <header className="page-head">
          <h1>Checks</h1>
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
          <h1>Checks</h1>
          <p className="lead">Only an admin can open this page.</p>
        </header>
        <Link href="/">Back to Ask about a policy</Link>
      </section>
    );
  }

  const primary = report?.checks.filter((check) => check.primary) ?? [];
  const rest = report?.checks.filter((check) => !check.primary) ?? [];
  const failed = report?.checks.some((check) => !check.ok) ?? false;

  return (
    <section className="stack">
      <header className="page-head">
        <h1>Checks</h1>
        <p className="lead">These checks show whether answers stay inside company policy.</p>
      </header>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {!report ? <p role="status">Loading…</p> : null}
      {report ? (
        <>
          <p className={report.status === "safe" ? "success" : "banner"}>{report.summary}</p>
          {report.ran_at ? <p className="whisper">Last checked {formatWhen(report.ran_at)}.</p> : null}
          {primary.length > 0 ? (
            <ul className="plain-list">
              {primary.map((check) => (
                <li key={check.name}>
                  <strong>{check.name}</strong>
                  <span className={check.ok ? "badge ok" : "badge bad"}>{check.ok ? "Passed" : "Did not pass"}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {rest.length > 0 ? (
            <>
              <h2>Also checked</h2>
              <ul className="plain-list">
                {rest.map((check) => (
                  <li key={check.name}>
                    <strong>{check.name}</strong>
                    <span className={check.ok ? "badge ok" : "badge bad"}>{check.ok ? "Passed" : "Did not pass"}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {failed ? (
            <details>
              <summary>Show details</summary>
              <ul>
                {report.checks
                  .filter((check) => !check.ok && check.developer_detail)
                  .map((check) => (
                    <li key={check.name}>
                      {check.name}: {check.developer_detail}
                    </li>
                  ))}
              </ul>
            </details>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
