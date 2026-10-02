"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { JobStageBody } from "@/components/job-stage-body";
import { JobStageNav, StagePager } from "@/components/job-stage-nav";
import { useJob } from "@/components/job-provider";
import { Shell } from "@/components/shell";
import { STAGES, stageIndex, type StageId } from "@/lib/api";
import { nextAction, statusClass, statusLabel } from "@/lib/labels";

function isStageId(value: string | undefined): value is StageId {
  return Boolean(value && STAGES.some((s) => s.id === value));
}

function stageFromPath(pathname: string): StageId | null {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "jobs" && parts.length >= 3 && isStageId(parts[2])) return parts[2];
  return null;
}

export function JobChrome({ children }: { children: React.ReactNode }) {
  const params = useParams<{ id: string; stage?: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const { detail, error, setError, viewingStage, setViewingStage } = useJob();

  const pathStage = stageFromPath(pathname) ?? (isStageId(params.stage) ? params.stage : null);
  const viewStage: StageId =
    viewingStage ?? pathStage ?? ((detail?.stage as StageId | undefined) || "upload");

  const [fadeTick, setFadeTick] = useState(0);
  const prevStage = useRef(viewStage);

  useLayoutEffect(() => {
    if (prevStage.current !== viewStage) {
      prevStage.current = viewStage;
      setFadeTick((n) => n + 1);
    }
  }, [viewStage]);

  useEffect(() => {
    if (pathStage) setViewingStage(pathStage);
  }, [pathStage, setViewingStage]);

  useEffect(() => {
    if (!detail || !params.id) return;
    const progress = stageIndex(detail.stage);
    const view = stageIndex(viewStage);
    if (view > progress) {
      const allowed = detail.stage as StageId;
      setViewingStage(allowed);
      router.replace(`/jobs/${params.id}/${allowed}`);
    }
  }, [detail, params.id, router, setViewingStage, viewStage]);

  const stageLabel = STAGES.find((s) => s.id === viewStage)?.label || viewStage;
  const isIndex = Boolean(pathname.match(/^\/jobs\/[^/]+\/?$/));

  return (
    <Shell>
      {!detail && !error ? (
        <div className="stack job-loading" aria-busy="true">
          <div className="skeleton-line w-40" />
          <div className="skeleton-line w-70" />
          <div className="skeleton-panel" />
        </div>
      ) : !detail ? (
        <div className="stack">
          <p className="error">{error}</p>
          <Link href="/">Back to jobs</Link>
        </div>
      ) : (
        <div className="stack job-workspace">
          <header className="page-head">
            <p className="kicker">
              <Link href="/">Jobs</Link> / {detail.id.slice(0, 8)} / {stageLabel}
            </p>
            <h1>{detail.filename}</h1>
            <p className="lede job-lede">
              <span className={statusClass(detail.status)}>{statusLabel(detail.status)}</span>
              <span className="lede-next">
                <strong>Next:</strong> {nextAction(detail)}
              </span>
            </p>
          </header>

          {!isIndex ? (
            <>
              <JobStageNav jobId={detail.id} jobStage={detail.stage} viewStage={viewStage} />

              {error ? (
                <p className="error error-banner">
                  <span>{error}</span>
                  <button type="button" className="ghost error-dismiss" onClick={() => setError("")}>
                    Dismiss
                  </button>
                </p>
              ) : null}

              <div key={fadeTick} className="stage-panel">
                <JobStageBody viewStage={viewStage} />
              </div>

              <StagePager jobId={detail.id} viewStage={viewStage} jobStage={detail.stage} detail={detail} />
            </>
          ) : (
            children
          )}
        </div>
      )}
    </Shell>
  );
}
