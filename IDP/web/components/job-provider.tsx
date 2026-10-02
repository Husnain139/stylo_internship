"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useParams } from "next/navigation";
import { api, type IdpException, type JobDetail, type StageId } from "@/lib/api";

type JobContextValue = {
  detail: JobDetail | null;
  error: string;
  pending: string;
  notes: Record<string, string>;
  viewingStage: StageId | null;
  setViewingStage: (stage: StageId) => void;
  setNotes: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setError: (value: string) => void;
  reload: () => Promise<JobDetail | null>;
  run: (label: string, task: () => Promise<unknown>) => Promise<void>;
  decide: (item: IdpException, decision: "approve" | "reject") => Promise<void>;
};

const JobContext = createContext<JobContextValue | null>(null);

function friendlyFetchError(reason: unknown): string {
  const message = reason instanceof Error ? reason.message : "Request failed";
  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return "Could not reach the API (is the backend running on :8000?). Try again.";
  }
  return message;
}

export function useJob(): JobContextValue {
  const ctx = useContext(JobContext);
  if (!ctx) throw new Error("useJob must be used under JobProvider");
  return ctx;
}

export function JobProvider({ children }: { children: ReactNode }) {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [viewingStage, setViewingStage] = useState<StageId | null>(null);

  const reload = useCallback(async () => {
    const next = await api<JobDetail>(`/api/jobs/${params.id}`);
    setDetail(next);
    setError("");
    return next;
  }, [params.id]);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setViewingStage(null);
    reload().catch((reason: Error) => {
      if (!cancelled) {
        setDetail(null);
        setError(friendlyFetchError(reason));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  useEffect(() => {
    if (!error || !detail) return;
    const timer = window.setTimeout(() => setError(""), 8000);
    return () => window.clearTimeout(timer);
  }, [error, detail]);

  const run = useCallback(
    async (label: string, task: () => Promise<unknown>) => {
      setPending(label);
      setError("");
      try {
        await task();
        await reload();
      } catch (reason) {
        setError(friendlyFetchError(reason));
      } finally {
        setPending("");
      }
    },
    [reload],
  );

  const decide = useCallback(
    async (item: IdpException, decision: "approve" | "reject") => {
      await run(`decide-${item.id}`, () =>
        api(`/api/jobs/${params.id}/exceptions/${item.id}/decide`, {
          method: "POST",
          body: JSON.stringify({ decision, note: notes[item.id] || null }),
        }),
      );
    },
    [notes, params.id, run],
  );

  const value = useMemo(
    () => ({
      detail,
      error,
      pending,
      notes,
      viewingStage,
      setViewingStage,
      setNotes,
      setError,
      reload,
      run,
      decide,
    }),
    [decide, detail, error, notes, pending, reload, run, viewingStage],
  );

  return <JobContext.Provider value={value}>{children}</JobContext.Provider>;
}
