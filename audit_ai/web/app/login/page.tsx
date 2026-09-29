"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { writeSession, type Role } from "@/lib/session";

const ACCOUNTS = [
  ["junior.auditor@stylo.local", "Junior Auditor"],
  ["senior.auditor@stylo.local", "Senior Auditor"],
  ["admin.auditor@stylo.local", "Administrator"],
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("senior.auditor@stylo.local");
  const [password, setPassword] = useState("prototype-only");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const result = await api<{ token: string; email: string; name: string; role: Role }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      writeSession(result);
      router.replace("/engagements");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign-in failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-shell" onSubmit={onSubmit}>
        <aside className="login-aside">
          <img className="login-logo" src="/logo.png" alt="Stylo" width={280} height={112} />
          <div className="login-aside-copy">
            <p className="kicker">Stylo audit desk</p>
            <h1>Document review that stays on this machine</h1>
            <p>
              Ingest procurement packs, confirm scope, and decide findings without sending files to a public model.
            </p>
          </div>
        </aside>

        <div className="login-main">
          <div className="login-main-head">
            <p className="kicker">Sign in</p>
            <h2>Enter the desk</h2>
            <p className="lede">
              Prototype accounts live only on this machine. The password below is not for real engagements.
            </p>
          </div>

          <div className="login-fields">
            <label>
              Email
              <input value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
              />
            </label>
          </div>

          {error ? <p className="error">{error}</p> : null}

          <button className="login-submit" type="submit" disabled={pending}>
            {pending ? "Signing in…" : "Enter the desk"}
          </button>

          <div className="login-accounts">
            <p className="scope-label">Prototype accounts</p>
            <ul className="account-list">
              {ACCOUNTS.map(([account, label]) => (
                <li key={account}>
                  <button
                    className={`account-pick${email === account ? " active" : ""}`}
                    type="button"
                    onClick={() => setEmail(account)}
                  >
                    <strong>{label}</strong>
                    <span>{account}</span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="muted login-hint">The desk only shows the actions that role is allowed to take.</p>
          </div>
        </div>
      </form>
    </main>
  );
}
