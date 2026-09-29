"use client";

import { useEffect, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { fetchPdfUrl } from "@/lib/api";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

export function PdfPane({ documentId, focusPage }: { documentId: string; focusPage?: number | null }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [pages, setPages] = useState(0);

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    fetchPdfUrl(documentId)
      .then((href) => {
        if (!active) {
          URL.revokeObjectURL(href);
          return;
        }
        objectUrl = href;
        setUrl(href);
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId]);

  useEffect(() => {
    if (!focusPage) return;
    document.getElementById(`pdf-page-${focusPage}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focusPage, pages]);

  if (error) return <p className="error">{error}</p>;
  if (!url) return <p className="muted">Loading the original PDF…</p>;

  return (
    <div className="pdf-frame">
      <Document
        file={url}
        loading={<p className="muted">Opening PDF…</p>}
        onLoadSuccess={({ numPages }) => setPages(numPages)}
        onLoadError={() => setError("The PDF viewer could not read this file.")}
      >
        {Array.from({ length: pages }, (_, index) => {
          const pageNumber = index + 1;
          return (
            <div id={`pdf-page-${pageNumber}`} key={pageNumber}>
              <Page pageNumber={pageNumber} width={560} />
            </div>
          );
        })}
      </Document>
    </div>
  );
}
