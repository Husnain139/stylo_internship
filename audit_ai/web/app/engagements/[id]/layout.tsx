"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { statusLabel, type Engagement } from "@/lib/types";

const TABS = [
  { href: "", label: "Overview" },
  { href: "/important", label: "Important data" },
  { href: "/analysis", label: "Analysis" },
  { href: "/review", label: "Review" },
];

export default function EngagementLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ id: string }>();
  const pathname = usePathname();
  const [engagement, setEngagement] = useState<Engagement | null>(null);

  useEffect(() => {
    api<Engagement>(`/engagements/${params.id}`)
      .then(setEngagement)
      .catch(() => setEngagement(null));
  }, [params.id, pathname]);

  return (
    <Shell>
      <div className="stack">
        <header className="page-head">
          <p className="kicker">Engagement</p>
          <div className="page-head-title">
            <h1>{engagement?.name ?? "Loading…"}</h1>
            {engagement ? (
              <span className={`pill pill-${engagement.scope_status}`}>{statusLabel(engagement.scope_status)}</span>
            ) : null}
          </div>
        </header>
        <nav className="tabs-bar" aria-label="Engagement sections">
          {TABS.map((tab) => {
            const href = `/engagements/${params.id}${tab.href}`;
            const active = pathname === href;
            return (
              <Link key={tab.label} href={href} className={active ? "active" : undefined}>
                {tab.label}
              </Link>
            );
          })}
        </nav>
        {children}
      </div>
    </Shell>
  );
}
