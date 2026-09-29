"use client";

import { FormEvent, useEffect, useState } from "react";
import { PageHead } from "@/components/page-head";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { roleLabel, useSession } from "@/lib/session";
import type { AuditEvent, AuditUser, Engagement } from "@/lib/types";
import { auditActionLabel, auditEventDetail, formatEngagementDate } from "@/lib/types";

export default function AdminPage() {
  const session = useSession();
  const [users, setUsers] = useState<AuditUser[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [retentionDays, setRetentionDays] = useState(2555);
  const [legalHold, setLegalHold] = useState(false);
  const [memberEmail, setMemberEmail] = useState("junior.auditor@stylo.local");
  const [engagementId, setEngagementId] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function reload() {
    const [nextUsers, nextEvents, nextEngagements, retention] = await Promise.all([
      api<AuditUser[]>("/users"),
      api<AuditEvent[]>("/audit-events"),
      api<Engagement[]>("/engagements"),
      api<{ retention_days: number; legal_hold: boolean }>("/settings/retention"),
    ]);
    setUsers(nextUsers);
    setEvents(nextEvents);
    setEngagements(nextEngagements);
    setEngagementId((current) => current || nextEngagements[0]?.id || "");
    setRetentionDays(retention.retention_days);
    setLegalHold(retention.legal_hold);
  }

  useEffect(() => {
    if (session?.role !== "administrator") return;
    let cancelled = false;
    Promise.all([
      api<AuditUser[]>("/users"),
      api<AuditEvent[]>("/audit-events"),
      api<Engagement[]>("/engagements"),
      api<{ retention_days: number; legal_hold: boolean }>("/settings/retention"),
    ])
      .then(([nextUsers, nextEvents, nextEngagements, retention]) => {
        if (cancelled) return;
        setUsers(nextUsers);
        setEvents(nextEvents);
        setEngagements(nextEngagements);
        setEngagementId((current) => current || nextEngagements[0]?.id || "");
        setRetentionDays(retention.retention_days);
        setLegalHold(retention.legal_hold);
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  async function saveRetention(event: FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await api("/settings/retention", {
        method: "PUT",
        body: JSON.stringify({ retention_days: retentionDays, legal_hold: legalHold }),
      });
      setMessage("Retention settings recorded. This prototype still has no deletion job.");
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save settings");
    }
  }

  async function assign(event: FormEvent) {
    event.preventDefault();
    if (!engagementId) return;
    setError("");
    try {
      await api(`/engagements/${engagementId}/members`, {
        method: "POST",
        body: JSON.stringify({ email: memberEmail }),
      });
      setMessage(`Assigned ${memberEmail}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not assign membership");
    }
  }

  return (
    <Shell>
      {!session ? (
        <p className="muted">Checking access…</p>
      ) : session.role !== "administrator" ? (
        <p>The administration desk is limited to the administrator role.</p>
      ) : (
        <div className="stack">
          <PageHead
            kicker="Control"
            title="Administration"
            lede="Users, retention, and the append-only trail. There is no delete control."
          />
          {error ? <p className="error">{error}</p> : null}
          {message ? <p className="notice">{message}</p> : null}
          <section className="panel">
            <h2>Users</h2>
            <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.name}</td>
                    <td>{user.email}</td>
                    <td>
                      <select
                        value={user.role}
                        disabled={user.email === session.email}
                        onChange={(event) => {
                          void api(`/users/${user.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({ role: event.target.value }),
                          }).then(reload);
                        }}
                      >
                        <option value="junior_auditor">{roleLabel("junior_auditor")}</option>
                        <option value="senior_auditor">{roleLabel("senior_auditor")}</option>
                        <option value="administrator">{roleLabel("administrator")}</option>
                      </select>
                    </td>
                    <td>{user.active ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </section>
          <form className="panel stack" onSubmit={assign}>
            <h2>Engagement membership</h2>
            <label>
              Engagement
              <select value={engagementId} onChange={(event) => setEngagementId(event.target.value)}>
                {engagements.map((engagement) => (
                  <option key={engagement.id} value={engagement.id}>
                    {engagement.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Email
              <input value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} />
            </label>
            <button type="submit">Grant membership</button>
          </form>
          <form className="panel stack" onSubmit={saveRetention}>
            <h2>Retention</h2>
            <label>
              Retention days
              <input
                type="number"
                min={1}
                value={retentionDays}
                onChange={(event) => setRetentionDays(Number(event.target.value))}
              />
            </label>
            <label className="inline">
              <input type="checkbox" checked={legalHold} onChange={(event) => setLegalHold(event.target.checked)} />
              Legal hold (recorded only; nothing is deleted)
            </label>
            <button type="submit">Save retention</button>
          </form>
          <section className="panel log">
            <h2>Audit trail</h2>
            <p className="muted">Newest first. Append-only; review decisions and notes appear here.</p>
            <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Detail</th>
                  <th>Object</th>
                </tr>
              </thead>
              <tbody>
                {events.length === 0 ? (
                  <tr>
                    <td colSpan={5}>No events yet.</td>
                  </tr>
                ) : (
                  events.map((event) => (
                    <tr key={event.id}>
                      <td className="created-at">{formatEngagementDate(event.ts_utc)}</td>
                      <td>{event.actor}</td>
                      <td>
                        <strong>{auditActionLabel(event.action)}</strong>
                        <br />
                        <code>{event.action}</code>
                      </td>
                      <td>{auditEventDetail(event) || "—"}</td>
                      <td>
                        {event.object_type}
                        <br />
                        <code>{event.object_id.slice(0, 8)}</code>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            </div>
          </section>
        </div>
      )}
    </Shell>
  );
}
