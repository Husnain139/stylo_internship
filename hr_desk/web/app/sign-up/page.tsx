"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { PasswordField } from "@/components/password-field";
import { useSession } from "@/components/session";

export default function SignUpPage() {
  const router = useRouter();
  const { me, signUp } = useSession();
  const emailId = useId();
  const emailHelpId = useId();
  const passwordId = useId();
  const ruleId = useId();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [emailInvalid, setEmailInvalid] = useState(false);
  const [passwordInvalid, setPasswordInvalid] = useState(false);
  const [busy, setBusy] = useState(false);
  const longEnough = password.length >= 8;

  useEffect(() => {
    if (me) router.replace("/");
  }, [me, router]);

  if (me) {
    return <p role="status">Signing in…</p>;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const missingEmail = email.trim() === "";
    const shortPassword = password.length < 8;
    setEmailInvalid(missingEmail);
    setPasswordInvalid(shortPassword);
    if (missingEmail || shortPassword) {
      setError(
        missingEmail && shortPassword
          ? "Enter your work email and a password of at least 8 characters."
          : missingEmail
            ? "Enter the work email HR has for you."
            : "Use at least 8 characters.",
      );
      return;
    }
    setError("");
    setBusy(true);
    try {
      await signUp(email.trim(), password);
      router.push("/");
    } catch (caught) {
      setEmailInvalid(true);
      setError(caught instanceof Error ? caught.message : "This email is not on the employee list.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack auth">
      <header className="page-head">
        <h1>Create a password</h1>
        <p className="lead">HR already has your name and email. You only choose a password.</p>
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
            Use the email on your employee record. Your name and role stay as they are.
          </p>
        </div>
        <div className="field">
          <label htmlFor={passwordId}>Password</label>
          <PasswordField
            id={passwordId}
            name="password"
            autoComplete="new-password"
            value={password}
            describedBy={ruleId}
            invalid={passwordInvalid}
            onChange={(value) => {
              setPassword(value);
              setPasswordInvalid(false);
            }}
          />
          <p id={ruleId} className={longEnough ? "requirement met" : passwordInvalid ? "requirement bad" : "requirement"}>
            {longEnough ? "Long enough to use." : "At least 8 characters."}
          </p>
        </div>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Creating your password…" : "Create password"}
        </button>
      </form>
      <p className="switch-line">
        Already have a password? <Link href="/sign-in">Sign in</Link>
      </p>
    </section>
  );
}
