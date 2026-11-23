"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { PasswordField } from "@/components/password-field";
import { useSession } from "@/components/session";
import { api } from "@/lib/api";

export default function SignUpPage() {
  const router = useRouter();
  const { me, localPasswordSetup, setInitialPassword, activate } = useSession();
  const emailId = useId();
  const passwordId = useId();
  const noteId = useId();
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const activation = !localPasswordSetup && Boolean(token);
  const needsPassword = localPasswordSetup || activation;

  useEffect(() => {
    const code = window.location.hash.slice(1);
    if (code) {
      setToken(code);
      window.history.replaceState(window.history.state, "", window.location.pathname);
    }
  }, []);

  useEffect(() => {
    if (me) router.replace("/");
  }, [me, router]);

  if (me) return <p role="status">Signing in...</p>;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (localPasswordSetup) {
        await setInitialPassword(email.trim(), password);
        router.replace("/");
      } else if (activation) {
        await activate(token, password);
        router.replace("/");
      } else {
        const response = await api<{ message: string }>("/api/sign-up", {
          method: "POST",
          body: JSON.stringify({ email: email.trim() }),
        });
        setMessage(response.message);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack auth">
      <header className="page-head">
        <h1>{activation ? "Choose a password" : "Set up your account"}</h1>
        {!needsPassword ? <p className="lead">We’ll email you a setup link.</p> : null}
      </header>
      <form className="panel" onSubmit={(event) => void submit(event)}>
        {!activation ? (
          <div className="field">
            <label htmlFor={emailId}>Work email</label>
            <input id={emailId} type="email" autoComplete="username" required maxLength={254}
              value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
        ) : null}
        {needsPassword ? (
          <div className="field">
            <label htmlFor={passwordId}>New password</label>
            <PasswordField id={passwordId} name="password" autoComplete="new-password"
              value={password} onChange={setPassword} describedBy={noteId} />
            <p className="help" id={noteId}>At least 12 characters.</p>
          </div>
        ) : null}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        {message ? <p className="success" role="status">{message}</p> : null}
        <button className="primary" disabled={busy || (needsPassword && password.length < 12)}>
          {busy ? (needsPassword ? "Saving…" : "Sending…") : needsPassword ? "Set password" : "Send setup link"}
        </button>
      </form>
      {activation ? <button type="button" onClick={() => { setToken(""); setPassword(""); setError(""); }}>
        Request a new setup link
      </button> : null}
      <p className="switch-line"><Link href="/sign-in">Back to sign in</Link></p>
    </section>
  );
}
