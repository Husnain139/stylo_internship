"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { readActor, writeActor } from "@/lib/api";

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [actor, setActor] = useState("finance_user");

  useEffect(() => {
    setActor(readActor());
  }, []);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="content-inner topbar-inner">
          <Link className="brand" href="/">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img className="brand-logo" src="/logo.png" alt="Stylo" width={148} height={56} />
            <span className="brand-copy">
              <strong>Document review</strong>
              <span>Finance &amp; Accounts · human review required</span>
            </span>
          </Link>
          <label className="actor-field">
            <span className="actor-hint">Your name (for the record)</span>
            <input
              value={actor}
              placeholder="Your name"
              onChange={(event) => {
                const next = event.target.value;
                setActor(next);
                writeActor(next);
              }}
            />
          </label>
        </div>
      </header>
      <nav className="subnav" aria-label="Workspace">
        <div className="content-inner subnav-inner">
          <Link href="/" className={pathname === "/" ? "active" : undefined}>
            My files
          </Link>
          <span className="role-mark">Review blanks, duplicates &amp; inconsistencies</span>
        </div>
      </nav>
      <main className="page">{children}</main>
    </div>
  );
}
