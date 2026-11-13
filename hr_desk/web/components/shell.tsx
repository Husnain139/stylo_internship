"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useSession } from "@/components/session";

const LINKS = [
  { href: "/", label: "Ask about a policy" },
  { href: "/policies", label: "Policies" },
  { href: "/questions", label: "Questions people asked" },
  { href: "/checks", label: "Checks" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { loading, me, people, signIn } = useSession();
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState("");

  async function choose(email: string) {
    setSwitchError("");
    setSwitching(true);
    try {
      await signIn(email);
    } catch (error) {
      setSwitchError(error instanceof Error ? error.message : "Choose a name from the list.");
    } finally {
      setSwitching(false);
    }
  }

  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="frame topbar-inner">
          <Link className="brand" href="/">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="Stylo" width={148} height={56} />
            <span>
              <strong>Policy help</strong>
              <span>Ask in plain language</span>
            </span>
          </Link>
          {me ? (
            <div className="who">
              <p>
                Signed in as {me.name}, {me.role}
              </p>
              <details>
                <summary>Switch person</summary>
                <PersonChoices people={people} busy={switching} onChoose={choose} />
              </details>
              {switchError ? (
                <p className="form-error" role="alert">
                  {switchError}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
        {me?.designation === "hr" ? (
          <nav className="nav" aria-label="Sections">
            <div className="frame nav-inner">
              {LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={pathname === link.href ? "page" : undefined}
                >
                  {link.label}
                </Link>
              ))}
            </div>
          </nav>
        ) : null}
      </header>
      <main id="main" className="frame page">
        {loading ? <p role="status">Loading…</p> : children}
      </main>
    </>
  );
}

export function PersonChoices({
  people,
  busy,
  onChoose,
}: {
  people: { email: string; name: string; role: string }[];
  busy: boolean;
  onChoose: (email: string) => void;
}) {
  return (
    <ul className="people">
      {people.map((person) => (
        <li key={person.email}>
          <button type="button" disabled={busy} onClick={() => onChoose(person.email)}>
            {person.name}, {person.role}
          </button>
        </li>
      ))}
    </ul>
  );
}
