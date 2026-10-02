"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { MouseEvent, ReactNode } from "react";
import { useJob } from "@/components/job-provider";
import { STAGES, stageIndex, type JobDetail, type StageId } from "@/lib/api";
import { pagerNextLabel } from "@/lib/labels";

export function jobStagePath(jobId: string, stage: StageId): string {
  return `/jobs/${jobId}/${stage}`;
}

/** Soft client nav — optimistic stage swap; no document view-transition. */
export function SoftLink({
  href,
  stage,
  className,
  children,
}: {
  href: string;
  stage: StageId;
  className?: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const { setViewingStage } = useJob();

  function onClick(event: MouseEvent<HTMLAnchorElement>) {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.altKey ||
      event.ctrlKey ||
      event.shiftKey
    ) {
      return;
    }
    event.preventDefault();
    setViewingStage(stage);
    router.push(href, { scroll: false });
  }

  return (
    <Link href={href} className={className} onClick={onClick} scroll={false} prefetch>
      {children}
    </Link>
  );
}

export function JobStageNav({
  jobId,
  jobStage,
  viewStage,
}: {
  jobId: string;
  jobStage: string;
  viewStage: StageId;
}) {
  const progress = stageIndex(jobStage);

  return (
    <ol className="stage-strip" aria-label="Review steps">
      {STAGES.map((stage, index) => {
        const reachable = index <= progress;
        const isView = stage.id === viewStage;
        const isCurrentPipeline = stage.id === jobStage;
        const isPast = reachable && index < progress && !isView;
        const className =
          [
            reachable ? "reachable" : "locked",
            isPast ? "done" : "",
            isCurrentPipeline ? "pipeline" : "",
            isView ? "viewing" : "",
          ]
            .filter(Boolean)
            .join(" ") || undefined;

        const inner = (
          <>
            <span className="stage-num">{index + 1}</span>
            <span className="stage-label">{stage.label}</span>
          </>
        );

        return (
          <li key={stage.id} className={className} aria-current={isView ? "step" : undefined}>
            {reachable ? (
              <SoftLink href={jobStagePath(jobId, stage.id)} stage={stage.id} className="stage-link">
                {inner}
              </SoftLink>
            ) : (
              <span className="stage-link disabled" aria-disabled="true" title="Finish earlier steps first">
                {inner}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function StagePager({
  jobId,
  viewStage,
  jobStage,
  detail,
}: {
  jobId: string;
  viewStage: StageId;
  jobStage: string;
  detail?: JobDetail | null;
}) {
  const progress = stageIndex(jobStage);
  const view = stageIndex(viewStage);
  const prev = view > 0 ? STAGES[view - 1] : null;
  const next = view < STAGES.length - 1 && view + 1 <= progress ? STAGES[view + 1] : null;
  const nextCopy =
    next && detail ? pagerNextLabel(viewStage, next.id, detail) : next ? `${next.label} →` : null;

  return (
    <div className="stage-pager actions">
      {prev ? (
        <SoftLink className="button-link ghost" href={jobStagePath(jobId, prev.id)} stage={prev.id}>
          ← {prev.label}
        </SoftLink>
      ) : (
        <span />
      )}
      {next && nextCopy ? (
        <SoftLink className="button-link" href={jobStagePath(jobId, next.id)} stage={next.id}>
          {nextCopy}
        </SoftLink>
      ) : null}
    </div>
  );
}
