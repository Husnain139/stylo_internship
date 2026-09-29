"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function EvidenceRedirectPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  useEffect(() => {
    router.replace(`/engagements/${params.id}/important`);
  }, [params.id, router]);

  return <p className="muted">Opening Important data…</p>;
}
