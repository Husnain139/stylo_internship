"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useJob } from "@/components/job-provider";
import { jobStagePath } from "@/components/job-stage-nav";
import type { StageId } from "@/lib/api";

/** Redirect /jobs/:id → /jobs/:id/:currentStage */
export default function JobIndexRedirect() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { detail } = useJob();

  useEffect(() => {
    if (!detail) return;
    router.replace(jobStagePath(params.id, (detail.stage || "upload") as StageId));
  }, [detail, params.id, router]);

  return <p className="muted">Opening current stage…</p>;
}
