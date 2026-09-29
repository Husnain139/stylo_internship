"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { PageHead } from "@/components/page-head";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { classLabel, formatEngagementDate, statusLabel, type Engagement } from "@/lib/types";

type DateSort = "newest" | "oldest";

function engagementSearchText(row: Engagement): string {
  const missing = row.missing_evidence.length ? row.missing_evidence.map(classLabel).join(" ") : "None noted";
  return [
    row.name,
    classLabel(row.proposed_type),
    statusLabel(row.scope_status),
    missing,
    formatEngagementDate(row.created_at),
  ]
    .join(" ")
    .toLowerCase();
}

export default function EngagementsPage() {
  const session = useSession();
  const [rows, setRows] = useState<Engagement[]>([]);
  const [name, setName] = useState("Procurement pack");
  const [assignAuditors, setAssignAuditors] = useState(true);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [query, setQuery] = useState("");
  const [dateSort, setDateSort] = useState<DateSort>("newest");
  const canCreate = session?.role === "junior_auditor" || session?.role === "senior_auditor";

  async function reload() {
    setRows(await api<Engagement[]>("/engagements"));
  }

  useEffect(() => {
    let cancelled = false;
    api<Engagement[]>("/engagements")
      .then((next) => {
        if (!cancelled) setRows(next);
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const list = needle ? rows.filter((row) => engagementSearchText(row).includes(needle)) : [...rows];
    list.sort((left, right) => {
      const delta = new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
      return dateSort === "newest" ? -delta : delta;
    });
    return list;
  }, [rows, query, dateSort]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await api("/engagements", {
        method: "POST",
        body: JSON.stringify({ name, assign_auditors: assignAuditors }),
      });
      setName("");
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create the engagement");
    } finally {
      setPending(false);
    }
  }

  return (
    <Shell>
      <div className="stack">
        <PageHead
          kicker="Workpapers"
          title="Engagements"
          lede="Each engagement keeps its own documents, raw fields, and processed findings."
        />
        {!session ? null : canCreate ? (
          <form className="panel stack" onSubmit={onCreate}>
            <label>
              New engagement
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label className="inline">
              <input
                type="checkbox"
                checked={assignAuditors}
                onChange={(event) => setAssignAuditors(event.target.checked)}
              />
              Assign every junior and senior auditor
            </label>
            <button type="submit" disabled={pending}>
              {pending ? "Creating…" : "Create engagement"}
            </button>
          </form>
        ) : (
          <p className="muted">Administrators assign membership from the administration desk. They do not open source files from here.</p>
        )}
        {error ? <p className="error">{error}</p> : null}
        <div className="panel">
          <div className="table-toolbar">
            <label>
              Search engagements
              <input
                type="search"
                value={query}
                placeholder="Name, scope, type, or date"
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            {query ? (
              <p className="muted">
                {visible.length} of {rows.length} shown
              </p>
            ) : null}
          </div>
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Proposed type</th>
                <th>Scope</th>
                <th>Missing evidence</th>
                <th>
                  <button
                    type="button"
                    className="sort-th"
                    aria-label={`Sort by created date, ${dateSort === "newest" ? "newest first" : "oldest first"}`}
                    onClick={() => setDateSort((current) => (current === "newest" ? "oldest" : "newest"))}
                  >
                    Created {dateSort === "newest" ? "↓" : "↑"}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={5}>No engagements yet.</td>
                </tr>
              ) : visible.length === 0 ? (
                <tr>
                  <td colSpan={5}>No engagements match your search.</td>
                </tr>
              ) : (
                visible.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <Link href={`/engagements/${row.id}`}>{row.name}</Link>
                    </td>
                    <td>{classLabel(row.proposed_type)}</td>
                    <td>
                      <span className={`pill pill-${row.scope_status}`}>{statusLabel(row.scope_status)}</span>
                    </td>
                    <td>{row.missing_evidence.length ? row.missing_evidence.map(classLabel).join(", ") : "None noted"}</td>
                    <td className="created-at" title={row.created_at}>
                      {formatEngagementDate(row.created_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </Shell>
  );
}
