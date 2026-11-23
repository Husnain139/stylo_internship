"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { useSession } from "@/components/session";
import { api, type EmployeeRow } from "@/lib/api";

import { DESIGNATIONS } from "@/lib/policy-roles";

export function PeopleScreen() {
  const { me, retry } = useSession();
  const emailId = useId();
  const nameId = useId();
  const designationId = useId();
  const adminId = useId();
  const errorId = useId();
  const [people, setPeople] = useState<EmployeeRow[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [designation, setDesignation] = useState("employee");
  const [isAdmin, setIsAdmin] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingRemove, setPendingRemove] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editRole, setEditRole] = useState("employee");
  const [editAdmin, setEditAdmin] = useState(false);

  useEffect(() => {
    if (!me?.isAdmin) return;
    api<{ employees: EmployeeRow[] }>("/api/employees")
      .then((data) => setPeople(data.employees))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Something went wrong. Try again."));
  }, [me?.isAdmin]);

  useEffect(() => {
    if (adding) document.getElementById(nameId)?.focus();
  }, [adding, nameId]);

  if (!me) {
    return (
      <section className="stack">
        <header className="page-head">
          <h1>People</h1>
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
          <h1>People</h1>
          <p className="lead">Only an admin can open this page.</p>
        </header>
        <Link href="/">Back to Ask HR</Link>
      </section>
    );
  }

  const invalidEmail = error.startsWith("Enter a valid email");
  const invalidName = error.startsWith("Enter this person's");
  const invalidDesignation = error.startsWith("Choose a role");

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api<{ message: string; employee: EmployeeRow }>("/api/employees", {
        method: "POST",
        body: JSON.stringify({ email, name, designation, is_admin: isAdmin }),
      });
      setMessage(result.message);
      setAdding(false);
      setEmail("");
      setName("");
      setDesignation("employee");
      setIsAdmin(false);
      const data = await api<{ employees: EmployeeRow[] }>("/api/employees");
      setPeople(data.employees);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack">
      <header className="page-head">
        <div className="section-heading">
          <h1>People</h1>
          {!adding ? <button className="primary" type="button" disabled={busy} onClick={() => {
            setAdding(true);
            setMessage("");
            setError("");
          }}>Add employee</button> : null}
        </div>
      </header>
      {error ? <p id={errorId} className="form-error" role="alert">{error}</p> : null}
      {message ? <p className="success" role="status">{message}</p> : null}
      {adding ? <form className="policy-form panel" onSubmit={onSubmit}>
        <h2>Add employee</h2>
        <div className="field">
          <label htmlFor={emailId}>Work email</label>
          <input
            id={emailId}
            type="email"
            autoComplete="off"
            required
            value={email}
            aria-invalid={invalidEmail || undefined}
            aria-describedby={invalidEmail ? errorId : undefined}
            onChange={(event) => setEmail(event.target.value)}
          />
          
        </div>
        <div className="field">
          <label htmlFor={nameId}>Name</label>
          <input
            id={nameId}
            required
            value={name}
            aria-invalid={invalidName || undefined}
            aria-describedby={invalidName ? errorId : undefined}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={designationId}>Role</label>
          <select
            id={designationId}
            value={designation}
            aria-invalid={invalidDesignation || undefined}
            aria-describedby={invalidDesignation ? errorId : undefined}
            onChange={(event) => setDesignation(event.target.value)}
          >
            {DESIGNATIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="check-row">
          <input
            id={adminId}
            type="checkbox"
            checked={isAdmin}
            onChange={(event) => setIsAdmin(event.target.checked)}
          />
          <label htmlFor={adminId}>Give admin access</label>
        </div>
        <div className="row-actions">
          <button className="primary" type="submit" disabled={busy}>{busy ? "Adding…" : "Add employee"}</button>
          <button type="button" disabled={busy} onClick={() => {
            setAdding(false);
            setEmail("");
            setName("");
            setDesignation("employee");
            setIsAdmin(false);
            setError("");
          }}>Cancel</button>
        </div>
      </form> : null}
      {people === null ? (
        !error ? <p role="status">Loading people…</p> : null
      ) : people.length === 0 ? (
        <p className="empty-state">No employees added yet.</p>
      ) : (
        <ul className="plain-list">
          {people.map((person) => (
            <li key={person.email}>
              <strong>{person.name}</strong>
              <span className="file-name">{person.email}</span>
              <span>
                {person.role}{person.isAdmin ? " · Admin" : ""}
                {!person.hasPassword ? " · Setup pending" : ""}
              </span>
              {editing === person.email ? (
                <div className="row-actions">
                  <label htmlFor={`role-${person.email}`}>Role</label>
                  <select
                    id={`role-${person.email}`}
                    value={editRole}
                    onChange={(event) => setEditRole(event.target.value)}
                  >
                    {DESIGNATIONS.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <span className="check-row">
                    <input
                      id={`admin-${person.email}`}
                      type="checkbox"
                      checked={editAdmin}
                      onChange={(event) => setEditAdmin(event.target.checked)}
                    />
                    <label htmlFor={`admin-${person.email}`}>Give admin access</label>
                  </span>
                  <button
                    type="button"
                    className="primary"
                    disabled={busy}
                    onClick={() => {
                      setBusy(true);
                      setError("");
                      setMessage("");
                      api<{ message: string }>(`/api/employees/${encodeURIComponent(person.email)}`, {
                        method: "PATCH",
                        body: JSON.stringify({ designation: editRole, is_admin: editAdmin }),
                      })
                        .then(async (result) => {
                          setMessage(result.message);
                          setEditing(null);
                          if (person.email === me.email) await retry();
                          const data = await api<{ employees: EmployeeRow[] }>("/api/employees");
                          setPeople(data.employees);
                        })
                        .catch((caught) =>
                          setError(caught instanceof Error ? caught.message : "Something went wrong. Try again."),
                        )
                        .finally(() => setBusy(false));
                    }}
                  >
                    Save changes
                  </button>
                  <button type="button" disabled={busy} onClick={() => setEditing(null)}>
                    Cancel
                  </button>
                </div>
              ) : person.email !== me.email && pendingRemove === person.email ? (
                <div className="row-actions">
                  <span>Remove {person.name}? They will no longer be able to sign in.</span>
                  <button
                    type="button"
                    className="danger"
                    disabled={busy}
                    onClick={() => {
                      setBusy(true);
                      setError("");
                      setMessage("");
                      api<{ message: string }>(`/api/employees/${encodeURIComponent(person.email)}`, {
                        method: "DELETE",
                      })
                        .then(async (result) => {
                          setMessage(result.message);
                          setPendingRemove(null);
                          const data = await api<{ employees: EmployeeRow[] }>("/api/employees");
                          setPeople(data.employees);
                        })
                        .catch((caught) =>
                          setError(caught instanceof Error ? caught.message : "Something went wrong. Try again."),
                        )
                        .finally(() => setBusy(false));
                    }}
                  >
                    Remove employee
                  </button>
                  <button type="button" disabled={busy} onClick={() => setPendingRemove(null)}>
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="row-actions">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setEditing(person.email);
                      setEditRole(person.designation);
                      setEditAdmin(person.isAdmin);
                      setPendingRemove(null);
                      setError("");
                      setMessage("");
                    }}
                  >
                    Edit access
                  </button>
                  {person.email === me.email ? null : (
                    <button
                      type="button"
                      className="danger"
                      disabled={busy}
                      onClick={() => {
                        setPendingRemove(person.email);
                        setEditing(null);
                        setError("");
                        setMessage("");
                      }}
                    >
                      Remove
                    </button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
