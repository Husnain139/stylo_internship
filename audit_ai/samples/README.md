# Sample document packs

All packs under this folder are **synthetic** or open-source test fixtures.
Do not add real invoices, payroll, or customer data here.

Regenerate with:

```bash
cd audit_ai/backend
python scripts/generate_samples.py
```

Packs:

- `mismatch` — Amount mismatch + missing approval. PO 200k vs invoice/payment 250k; approval not found. Default demo pack.
- `clean` — Clean match. PO, invoice, and payment agree at 180k with approval on file.
- `missing_po` — Invoice without matching PO. Invoice references a PO that is not in the pack.
- `duplicate_payment` — Duplicate payment candidate. Two payments share vendor, amount, and date.
- `partial` — Incomplete evidence set. Missing payment — scope should list missing evidence.
- `multi_vendor` — Two vendor streams. Two clean PO/invoice/payment chains plus one shared policy.
- `kitchen_sink` — All finding types. Mismatch, unmatched PO, duplicate payment, and a memo in one engagement.
- `scanned` — Scanned image-only pack (OCR path). Full pack rendered as image-only PDFs — no text layer. Expect unknown/empty extract until local OCR exists. (4 PNG scans in `images/scanned/`)
- `hybrid` — Hybrid text + scanned invoice. Text PO/payment/policy with an image-only invoice. Tests mixed evidence quality. (1 PNG scans in `images/hybrid/`)
- `noise` — Noise + unknown docs. Internal memo plus open-source PDF fixtures. Scope incomplete. (1 PNG scans in `images/noise/`)

## OCR / scanned fixtures

- `scanned/` — image-only PDFs (no text layer).
- `hybrid/` — text docs plus one scanned invoice PDF.
- `images/<pack>/` — PNG scans for offline OCR experiments.
- The prototype uploader accepts PDF today; PNGs are for OCR tooling beside the app.

`external/` holds Mozilla pdf.js open-source fixtures used as unknown noise.
