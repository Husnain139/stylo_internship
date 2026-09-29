"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { readSession } from "@/lib/session";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(readSession() ? "/engagements" : "/login");
  }, [router]);
  return <p className="page muted">Opening the reviewer…</p>;
}
