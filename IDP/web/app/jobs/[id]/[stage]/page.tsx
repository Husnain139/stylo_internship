"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useJob } from "@/components/job-provider";
import { jobStagePath } from "@/components/job-stage-nav";
import { STAGES, stageIndex, type StageId } from "@/lib/api";

function isStageId(value: string): value is StageId {
  return STAGES.some((s) => s.id === value);
}

/**
 * Stage routes exist for shareable URLs. Stage UI lives in JobChrome so the
 * shell/header/nav stay mounted across soft navigations.
 */
export default function JobStagePage() {
  const params = useParams<{ id: string; stage: string }>();
  const router = useRouter();
  const { detail, setViewingStage } = useJob();

  useEffect(() => {
    if (!isStageId(params.stage)) {
      router.replace(jobStagePath(params.id, "upload"));
      return;
    }
    setViewingStage(params.stage);
  }, [params.id, params.stage, router, setViewingStage]);

  useEffect(() => {
    if (!detail || !isStageId(params.stage)) return;
    const progress = stageIndex(detail.stage);
    const view = stageIndex(params.stage);
    if (view > progress) {
      router.replace(jobStagePath(params.id, detail.stage as StageId));
    }
  }, [detail, params.id, params.stage, router]);

  return null;
}
