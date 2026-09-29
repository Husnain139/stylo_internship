"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { classLabel, fieldLabel, statusLabel, type AuditDocument, type EvidenceField } from "@/lib/types";

const PdfPane = dynamic(() => import("@/components/pdf-pane").then((mod) => mod.PdfPane), {
  ssr: false,
  loading: () => <p className="muted">Preparing the PDF viewer…</p>,
});

const CLASS_ORDER = ["purchase_order", "invoice", "payment", "policy"];
const FIELD_ORDER = [
  "po_number",
  "invoice_id",
  "payment_id",
  "policy_name",
  "vendor",
  "po_date",
  "invoice_date",
  "payment_date",
  "amount",
  "tax",
  "spending_limit",
  "approval_required_above",
  "po_reference",
  "reference",
  "approved_by",
  "approval_status",
];

function byClass(left: AuditDocument, right: AuditDocument): number {
  const leftIndex = CLASS_ORDER.indexOf(left.document_class ?? "");
  const rightIndex = CLASS_ORDER.indexOf(right.document_class ?? "");
  return (leftIndex === -1 ? CLASS_ORDER.length : leftIndex) - (rightIndex === -1 ? CLASS_ORDER.length : rightIndex);
}

function orderedFields(document: AuditDocument): EvidenceField[] {
  return [...(document.fields ?? [])].sort((left, right) => {
    const leftSchema = left.source === "schema" ? 0 : 1;
    const rightSchema = right.source === "schema" ? 0 : 1;
    if (leftSchema !== rightSchema) return leftSchema - rightSchema;
    const leftIndex = FIELD_ORDER.indexOf(left.field_name);
    const rightIndex = FIELD_ORDER.indexOf(right.field_name);
    return (leftIndex === -1 ? FIELD_ORDER.length : leftIndex) - (rightIndex === -1 ? FIELD_ORDER.length : rightIndex);
  });
}

function schemaFields(document: AuditDocument): EvidenceField[] {
  return orderedFields(document).filter((field) => field.source === "schema");
}

function factTitle(document: AuditDocument, field: EvidenceField): string {
  if (field.field_name === "amount") return `${classLabel(document.document_class)} amount`;
  if (field.field_name === "tax") return "Invoice tax";
  if (field.field_name === "spending_limit") return "Spending limit";
  if (field.field_name === "approval_required_above") return "Approval required above";
  if (field.field_name === "approval_status") return "Invoice approval";
  return fieldLabel(field.field_name);
}

export default function ImportantDataPage() {
  const params = useParams<{ id: string }>();
  const [documents, setDocuments] = useState<AuditDocument[]>([]);
  const [selected, setSelected] = useState("");
  const [focusPage, setFocusPage] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api<{ documents: AuditDocument[] }>(`/engagements/${params.id}/evidence`)
      .then((payload) => {
        if (cancelled) return;
        const ordered = [...payload.documents].sort(byClass);
        setDocuments(ordered);
        setSelected((current) => current || ordered[0]?.id || "");
        setReady(true);
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setError(reason.message);
          setReady(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  const current = documents.find((document) => document.id === selected);
  const facts = documents.flatMap((document) =>
    schemaFields(document)
      .filter((field) =>
        ["amount", "tax", "spending_limit", "approval_required_above", "approval_status"].includes(field.field_name),
      )
      .map((field) => ({ key: `${document.id}-${field.id}`, title: factTitle(document, field), field })),
  );
  const seenFacts = new Set<string>();
  const distinctFacts = facts.filter((fact) => {
    const key = `${fact.title}|${fact.field.value ?? ""}|${fact.field.validation_status}`;
    if (seenFacts.has(key)) return false;
    seenFacts.add(key);
    return true;
  });

  return (
    <div className="stack">
      <section className="banner">
        <strong>Important data</strong>
        Extracted field values with page references and the PDF. Amounts stay as copied from the documents. Analysis on
        the next screen is a separate result.
      </section>
      {error ? <p className="error">{error}</p> : null}
      {ready && documents.length === 0 && !error ? (
        <p className="muted">Ingest documents on the overview before important data can be shown.</p>
      ) : null}
      {distinctFacts.length > 0 ? (
        <div className="facts">
          {distinctFacts.map((fact) => (
            <article key={fact.key} className="fact">
              <span className="label">{fact.title}</span>
              <strong>{fact.field.value ?? "Not found"}</strong>
              <span className={`pill pill-${fact.field.validation_status}`}>{statusLabel(fact.field.validation_status)}</span>
            </article>
          ))}
        </div>
      ) : null}
      {documents.length > 0 ? (
        <div className="split">
          <div className="stack">
            {documents.map((document) => (
              <button
                key={document.id}
                type="button"
                className={`doc-button${document.id === selected ? " active" : ""}`}
                onClick={() => {
                  setSelected(document.id);
                  setFocusPage(null);
                }}
              >
                {document.filename}
                <br />
                <small>{classLabel(document.document_class)}</small>
              </button>
            ))}
          </div>
          <div className="stack">
            {current ? <PdfPane key={current.id} documentId={current.id} focusPage={focusPage} /> : null}
            <div className="panel">
              <div className="table-wrap">
                <table>
                  <caption className="muted">
                    Extracted fields for {current ? classLabel(current.document_class).toLowerCase() : "the selected document"}
                  </caption>
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Value</th>
                      <th>Page</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(current ? orderedFields(current) : []).map((field) => (
                      <tr key={field.id}>
                        <td>
                          {fieldLabel(field.field_name)}
                          {field.source !== "schema" ? <span className="muted"> · noted</span> : null}
                        </td>
                        <td>{field.value ?? "Not found"}</td>
                        <td>
                          {field.page ? (
                            <button className="secondary" type="button" onClick={() => setFocusPage(field.page)}>
                              p.{field.page}
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          <span className={`pill pill-${field.validation_status}`}>{statusLabel(field.validation_status)}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
