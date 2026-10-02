"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { DragEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Shell } from "@/components/shell";
import { api, uploadFile, type JobSummary } from "@/lib/api";
import { formatUpdatedAt, stageLabel, statusClass, statusLabel } from "@/lib/labels";

export default function HomePage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const dropzoneRef = useRef<HTMLFormElement>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [selectedName, setSelectedName] = useState("");

  const reload = useCallback(async () => {
    const data = await api<{ jobs: JobSummary[] }>("/api/jobs");
    setJobs(data.jobs);
  }, []);

  useEffect(() => {
    let cancelled = false;
    reload()
      .then(() => {
        if (!cancelled) setError("");
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  async function handleFiles(files: File[]) {
    if (!files.length) return;
    setSelectedName(files[0].name);
    setPending(true);
    setError("");
    try {
      const job = await uploadFile(files[0]);
      router.push(`/jobs/${job.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed");
      setPending(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const files = inputRef.current?.files;
    void handleFiles(files ? Array.from(files) : []);
  }

  function onDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragging(false);
    void handleFiles(Array.from(event.dataTransfer.files ?? []));
  }

  function focusUpload() {
    dropzoneRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    inputRef.current?.click();
  }

  return (
    <Shell>
      <div className="stack">
        <header className="page-head home-head">
          <p className="kicker">Finance &amp; Accounts</p>
          <h1>Document review</h1>
          <p className="lede">
            Upload a ledger or invoice file. We highlight blanks, duplicates, and other inconsistencies.
            You review and decide, then download the finished file.
          </p>
        </header>

        <form
          ref={dropzoneRef}
          className={`panel dropzone ${dragging ? "dragging" : ""} ${pending ? "pending" : ""}`}
          onSubmit={onSubmit}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <h2>Upload a file</h2>
          {pending ? (
            <p className="dropzone-copy upload-pending">
              Receiving your file… next you&apos;ll choose what blanks and duplicates to fix.
            </p>
          ) : (
            <p className="dropzone-copy">
              Drop one spreadsheet, PDF, Word file, or scan. Large spreadsheets are fine. After upload
              you prepare the file, review findings, then download.
            </p>
          )}
          <input
            ref={inputRef}
            id="idp-file"
            className="file-input-hidden"
            type="file"
            accept=".xlsx,.xls,.csv,.pdf,.docx,.doc,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp"
            required
            disabled={pending}
            onChange={() => {
              const name = inputRef.current?.files?.[0]?.name || "";
              setSelectedName(name);
            }}
          />
          <div className="dropzone-actions">
            <button
              type="button"
              className="ghost"
              disabled={pending}
              onClick={() => inputRef.current?.click()}
            >
              Choose file
            </button>
            <button type="submit" disabled={pending}>
              {pending ? "Receiving…" : "Upload & continue"}
            </button>
            {selectedName ? (
              <span className="file-chip" title={selectedName}>
                <span>{selectedName}</span>
              </span>
            ) : (
              <span className="muted">No file selected</span>
            )}
          </div>
        </form>

        {error ? <p className="error">{error}</p> : null}

        <section className="panel jobs-panel">
          <div className="panel-head">
            <h2>Recent files</h2>
            <button type="button" className="ghost" onClick={() => void reload().catch(() => undefined)}>
              Refresh
            </button>
          </div>
          {jobs.length === 0 ? (
            <div className="empty-state">
              <p>No files yet — upload a finance document to begin.</p>
              <button type="button" onClick={focusUpload}>
                Upload a file
              </button>
            </div>
          ) : (
            <div className="table-wrap jobs-table-wrap">
              <table className="jobs-table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Step</th>
                    <th>Status</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr
                      key={job.id}
                      className="jobs-row"
                      tabIndex={0}
                      onClick={() => router.push(`/jobs/${job.id}`)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          router.push(`/jobs/${job.id}`);
                        }
                      }}
                    >
                      <td>
                        <Link
                          href={`/jobs/${job.id}`}
                          className="jobs-file"
                          onClick={(event) => event.stopPropagation()}
                        >
                          {job.filename}
                        </Link>
                      </td>
                      <td>
                        <span className="pill stage-pill">{stageLabel(job.stage)}</span>
                      </td>
                      <td>
                        <span className={statusClass(job.status)}>{statusLabel(job.status)}</span>
                      </td>
                      <td className="muted" title={new Date(job.updated_at).toLocaleString()}>
                        {formatUpdatedAt(job.updated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </Shell>
  );
}
