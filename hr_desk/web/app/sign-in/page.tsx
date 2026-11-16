"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { PasswordField } from "@/components/password-field";
import { useSession } from "@/components/session";

export default function SignInPage() {
  const router = useRouter();
  const { me, signIn } = useSession();
  const emailId = useId();
  const emailHelpId = useId();
  const passwordId = useId();
  const passwordHelpId = useId();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [emailInvalid, setEmailInvalid] = useState(false);
  const [passwordInvalid, setPasswordInvalid] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (me) router.replace("/");
  }, [me, router]);

  if (me) {
    return <p role="status">Signing in…</p>;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const missingEmail = email.trim() === "";
    const missingPassword = password === "";
    setEmailInvalid(missingEmail);
    setPasswordInvalid(missingPassword);
    if (missingEmail || missingPassword) {
      setError(
        missingEmail && missingPassword
          ? "Enter your work email and password."
          : missingEmail
            ? "Enter your work email."
            : "Enter your password.",
      );
      return;
    }
    setError("");
    setBusy(true);
    try {
      await signIn(email.trim(), password);
      router.push("/");
    } catch (caught) {
      setEmailInvalid(true);
      setPasswordInvalid(true);
      setError(caught instanceof Error ? caught.message : "The email or password does not match.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack auth">
      <header className="page-head">
        <h1>Sign in</h1>
        <p className="lead">Use the work email and password you created for HR Desk.</p>
      </header>
      <form className="panel" noValidate onSubmit={(event) => void submit(event)}>
        <div className="field">
          <label htmlFor={emailId}>Work email</label>
          <input
            id={emailId}
            name="email"
            type="email"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            inputMode="email"
            value={email}
            aria-invalid={emailInvalid || undefined}
            aria-describedby={emailHelpId}
            onChange={(event) => {
              setEmail(event.target.value);
              setEmailInvalid(false);
            }}
          />
          <p id={emailHelpId} className="help">
            The email on your employee record.
          </p>
        </div>
        <div className="field">
          <label htmlFor={passwordId}>Password</label>
          <PasswordField
            id={passwordId}
            name="password"
            autoComplete="current-password"
            value={password}
            describedBy={passwordHelpId}
            invalid={passwordInvalid}
            onChange={(value) => {
              setPassword(value);
              setPasswordInvalid(false);
            }}
          />
          <p id={passwordHelpId} className="help">
            The password you chose for HR Desk.
          </p>
        </div>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="switch-line">
        First time here? <Link href="/sign-up">Create a password</Link>
      </p>
    </section>
  );
}
