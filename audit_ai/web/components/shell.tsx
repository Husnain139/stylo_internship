"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { clearSession, readSession, roleLabel, useSession } from "@/lib/session";

function backTarget(pathname: string): string | null {
  const match = pathname.match(/^\/engagements\/([^/]+)(\/.*)?$/);
  if (!match) return null;
  if (match[2]) return `/engagements/${match[1]}`;
  return "/engagements";
}

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const session = useSession();

  useEffect(() => {
    if (!readSession()) router.replace("/login");
  }, [router, pathname, session]);

  if (!session) {
    return (
      <div className="shell">
        <main className="page">
          <p className="loading-note muted">Checking session…</p>
        </main>
      </div>
    );
  }

  const backHref = backTarget(pathname);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="content-inner topbar-inner">
          <Link className="brand" href="/engagements">
            <img className="brand-logo" src="/logo.png" alt="Stylo" width={160} height={64} />
            <span className="brand-copy">
              <strong>Audit Document Reviewer</strong>
              <span>Company prototype · documents stay on this machine</span>
            </span>
          </Link>
          <button
            className="secondary"
            type="button"
            onClick={() => {
              void api("/auth/logout", { method: "POST" })
                .catch(() => undefined)
                .finally(() => {
                  clearSession();
                  router.replace("/login");
                });
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <nav className="subnav" aria-label="Workspace">
        <div className="content-inner subnav-inner">
          <div className="subnav-links">
            {backHref ? (
              <Link className="back-link" href={backHref} aria-label="Back">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M14.5 6.5 9 12l5.5 5.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </Link>
            ) : null}
            <Link href="/engagements" className={pathname.startsWith("/engagements") ? "active" : undefined}>
              Engagements
            </Link>
            {session.role === "administrator" ? (
              <Link href="/admin" className={pathname.startsWith("/admin") ? "active" : undefined}>
                Administration
              </Link>
            ) : null}
          </div>
          <span className="role-mark">{roleLabel(session.role)}</span>
        </div>
      </nav>
      <main className="page">{children}</main>
    </div>
  );
}
