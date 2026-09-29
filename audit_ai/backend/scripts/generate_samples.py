"""Create synthetic procurement PDFs/images for local testing. Safe to commit.

Also downloads small open-source non-procurement fixtures used as noise.
Those files are public test assets, not real business records.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import samples_dir
from app.pdf_text import write_sample_pdf, write_scan_png, write_scanned_pdf

# Open-source Mozilla pdf.js fixtures (public test PDFs, not business documents).
EXTERNAL_FIXTURES = {
    "tracemonkey.pdf": (
        "https://raw.githubusercontent.com/mozilla/pdf.js/ba2edeae/web/"
        "compressed.tracemonkey-pldi-09.pdf"
    ),
    "pdfjs_faq.pdf": "https://cdn.jsdelivr.net/gh/mozilla/pdf.js@ba2edeae/web/compressed.tracemonkey-pldi-09.pdf",
}


def _lines(*rows: str) -> list[str]:
    return ["\n".join(rows)]


PACKS: dict[str, dict] = {
    "mismatch": {
        "title": "Amount mismatch + missing approval",
        "description": "PO 200k vs invoice/payment 250k; approval not found. Default demo pack.",
        "expected_rules": ["AMOUNT_MISMATCH", "MISSING_APPROVAL"],
        "files": {
            "purchase_order.pdf": _lines(
                "PURCHASE ORDER",
                "PO Number: PO-7781",
                "Vendor: ABC Supplies",
                "Date: 01 August 2026",
                "Amount: PKR 200,000",
                "Description: Office supplies",
                "Approved by: Procurement Manager",
            ),
            "invoice.pdf": [
                "\n".join(
                    [
                        "INVOICE",
                        "Invoice ID: INV-1042",
                        "Vendor: ABC Supplies",
                        "Invoice date: 12 August 2026",
                        "PO Reference: PO-7781",
                        "Description: Office supplies",
                        "Approval status: Not found",
                    ]
                ),
                "\n".join(
                    [
                        "INVOICE INV-1042",
                        "Amount: PKR 250,000",
                        "Tax: PKR 45,000",
                    ]
                ),
            ],
            "payment.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-551",
                "Vendor: ABC Supplies",
                "Date: 20 August 2026",
                "Amount: PKR 250,000",
                "Reference: INV-1042",
            ),
            "approval_policy.pdf": _lines(
                "APPROVAL POLICY",
                "Policy name: Procurement Approval Policy",
                "Spending limit: PKR 200,000",
                "Approval required above: PKR 200,000",
                "Purchases above the spending limit require documented approval before payment.",
            ),
        },
    },
    "clean": {
        "title": "Clean match",
        "description": "PO, invoice, and payment agree at 180k with approval on file.",
        "expected_rules": [],
        "files": {
            "purchase_order.pdf": _lines(
                "PURCHASE ORDER",
                "PO Number: PO-9001",
                "Vendor: Contoso Stationery",
                "Date: 03 July 2026",
                "Amount: PKR 180,000",
                "Description: Quarterly stationery",
                "Approved by: Finance Controller",
            ),
            "invoice.pdf": _lines(
                "INVOICE",
                "Invoice ID: INV-2201",
                "Vendor: Contoso Stationery",
                "Invoice date: 10 July 2026",
                "PO Reference: PO-9001",
                "Description: Quarterly stationery",
                "Approval status: Approved",
                "Amount: PKR 180,000",
                "Tax: PKR 0",
            ),
            "payment.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-880",
                "Vendor: Contoso Stationery",
                "Date: 18 July 2026",
                "Amount: PKR 180,000",
                "Reference: INV-2201",
            ),
            "approval_policy.pdf": _lines(
                "APPROVAL POLICY",
                "Policy name: Contoso Spend Control",
                "Spending limit: PKR 200,000",
                "Approval required above: PKR 200,000",
            ),
        },
    },
    "missing_po": {
        "title": "Invoice without matching PO",
        "description": "Invoice references a PO that is not in the pack.",
        "expected_rules": ["UNMATCHED_INVOICE"],
        "files": {
            "purchase_order.pdf": _lines(
                "PURCHASE ORDER",
                "PO Number: PO-1111",
                "Vendor: Other Vendor Ltd",
                "Date: 01 June 2026",
                "Amount: PKR 50,000",
                "Description: Unrelated order",
                "Approved by: Buyer",
            ),
            "invoice.pdf": _lines(
                "INVOICE",
                "Invoice ID: INV-4400",
                "Vendor: Orphan Goods",
                "Invoice date: 08 June 2026",
                "PO Reference: PO-9999",
                "Description: Unlinked goods",
                "Approval status: Approved",
                "Amount: PKR 95,000",
                "Tax: PKR 5,000",
            ),
            "payment.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-440",
                "Vendor: Orphan Goods",
                "Date: 15 June 2026",
                "Amount: PKR 95,000",
                "Reference: INV-4400",
            ),
            "approval_policy.pdf": _lines(
                "APPROVAL POLICY",
                "Policy name: Standard Policy",
                "Spending limit: PKR 500,000",
                "Approval required above: PKR 500,000",
            ),
        },
    },
    "duplicate_payment": {
        "title": "Duplicate payment candidate",
        "description": "Two payments share vendor, amount, and date.",
        "expected_rules": ["DUPLICATE_PAYMENT"],
        "files": {
            "purchase_order.pdf": _lines(
                "PURCHASE ORDER",
                "PO Number: PO-5500",
                "Vendor: Twin Pay Co",
                "Date: 02 May 2026",
                "Amount: PKR 75,000",
                "Description: Maintenance",
                "Approved by: Ops Lead",
            ),
            "invoice.pdf": _lines(
                "INVOICE",
                "Invoice ID: INV-5500",
                "Vendor: Twin Pay Co",
                "Invoice date: 09 May 2026",
                "PO Reference: PO-5500",
                "Description: Maintenance",
                "Approval status: Approved",
                "Amount: PKR 75,000",
                "Tax: PKR 0",
            ),
            "payment.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-701",
                "Vendor: Twin Pay Co",
                "Date: 12 May 2026",
                "Amount: PKR 75,000",
                "Reference: INV-5500",
            ),
            "payment_copy.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-702",
                "Vendor: Twin Pay Co",
                "Date: 12 May 2026",
                "Amount: PKR 75,000",
                "Reference: INV-5500",
            ),
            "approval_policy.pdf": _lines(
                "APPROVAL POLICY",
                "Policy name: Twin Pay Policy",
                "Spending limit: PKR 100,000",
                "Approval required above: PKR 100,000",
            ),
        },
    },
    "partial": {
        "title": "Incomplete evidence set",
        "description": "Missing payment — scope should list missing evidence.",
        "expected_rules": [],
        "files": {
            "purchase_order.pdf": _lines(
                "PURCHASE ORDER",
                "PO Number: PO-3300",
                "Vendor: Partial Pack Ltd",
                "Date: 14 April 2026",
                "Amount: PKR 40,000",
                "Description: Partial pack",
                "Approved by: Clerk",
            ),
            "invoice.pdf": _lines(
                "INVOICE",
                "Invoice ID: INV-3300",
                "Vendor: Partial Pack Ltd",
                "Invoice date: 20 April 2026",
                "PO Reference: PO-3300",
                "Description: Partial pack",
                "Approval status: Approved",
                "Amount: PKR 40,000",
                "Tax: PKR 0",
            ),
            "approval_policy.pdf": _lines(
                "APPROVAL POLICY",
                "Policy name: Partial Pack Policy",
                "Spending limit: PKR 100,000",
                "Approval required above: PKR 100,000",
            ),
        },
    },
    "multi_vendor": {
        "title": "Two vendor streams",
        "description": "Two clean PO/invoice/payment chains plus one shared policy.",
        "expected_rules": [],
        "files": {
            "po_alpha.pdf": _lines(
                "PURCHASE ORDER",
                "PO Number: PO-A100",
                "Vendor: Alpha Traders",
                "Date: 01 March 2026",
                "Amount: PKR 120,000",
                "Description: Hardware",
                "Approved by: IT Buyer",
            ),
            "invoice_alpha.pdf": _lines(
                "INVOICE",
                "Invoice ID: INV-A100",
                "Vendor: Alpha Traders",
                "Invoice date: 08 March 2026",
                "PO Reference: PO-A100",
                "Description: Hardware",
                "Approval status: Approved",
                "Amount: PKR 120,000",
                "Tax: PKR 0",
            ),
            "payment_alpha.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-A100",
                "Vendor: Alpha Traders",
                "Date: 15 March 2026",
                "Amount: PKR 120,000",
                "Reference: INV-A100",
            ),
            "po_beta.pdf": _lines(
                "PURCHASE ORDER",
                "PO Number: PO-B200",
                "Vendor: Beta Paper Co",
                "Date: 02 March 2026",
                "Amount: PKR 35,000",
                "Description: Paper stock",
                "Approved by: Admin",
            ),
            "invoice_beta.pdf": _lines(
                "INVOICE",
                "Invoice ID: INV-B200",
                "Vendor: Beta Paper Co",
                "Invoice date: 09 March 2026",
                "PO Reference: PO-B200",
                "Description: Paper stock",
                "Approval status: Approved",
                "Amount: PKR 35,000",
                "Tax: PKR 0",
            ),
            "payment_beta.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-B200",
                "Vendor: Beta Paper Co",
                "Date: 16 March 2026",
                "Amount: PKR 35,000",
                "Reference: INV-B200",
            ),
            "approval_policy.pdf": _lines(
                "APPROVAL POLICY",
                "Policy name: Multi Vendor Policy",
                "Spending limit: PKR 250,000",
                "Approval required above: PKR 250,000",
            ),
        },
    },
    "kitchen_sink": {
        "title": "All finding types",
        "description": "Mismatch, unmatched PO, duplicate payment, and a memo in one engagement.",
        "expected_rules": [
            "AMOUNT_MISMATCH",
            "MISSING_APPROVAL",
            "UNMATCHED_INVOICE",
            "DUPLICATE_PAYMENT",
        ],
        "files": {
            "po_match.pdf": _lines(
                "PURCHASE ORDER",
                "PO Number: PO-KS1",
                "Vendor: Sink Supplies",
                "Date: 01 September 2026",
                "Amount: PKR 100,000",
                "Description: Mixed kit",
                "Approved by: Buyer",
            ),
            "invoice_over.pdf": [
                "\n".join(
                    [
                        "INVOICE",
                        "Invoice ID: INV-KS1",
                        "Vendor: Sink Supplies",
                        "Invoice date: 05 September 2026",
                        "PO Reference: PO-KS1",
                        "Description: Mixed kit",
                        "Approval status: Not found",
                    ]
                ),
                "\n".join(
                    [
                        "INVOICE INV-KS1",
                        "Amount: PKR 160,000",
                        "Tax: PKR 10,000",
                    ]
                ),
            ],
            "invoice_orphan.pdf": _lines(
                "INVOICE",
                "Invoice ID: INV-KS9",
                "Vendor: Ghost Vendor",
                "Invoice date: 06 September 2026",
                "PO Reference: PO-GONE",
                "Description: Orphan line",
                "Approval status: Approved",
                "Amount: PKR 22,000",
                "Tax: PKR 0",
            ),
            "payment_a.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-KS1",
                "Vendor: Sink Supplies",
                "Date: 10 September 2026",
                "Amount: PKR 160,000",
                "Reference: INV-KS1",
            ),
            "payment_b.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-KS2",
                "Vendor: Sink Supplies",
                "Date: 10 September 2026",
                "Amount: PKR 160,000",
                "Reference: INV-KS1",
            ),
            "approval_policy.pdf": _lines(
                "APPROVAL POLICY",
                "Policy name: Kitchen Sink Policy",
                "Spending limit: PKR 120,000",
                "Approval required above: PKR 120,000",
            ),
            "internal_memo.pdf": _lines(
                "INTERNAL MEMO",
                "Subject: Ignore this for classification",
                "Not a procurement form.",
            ),
        },
    },
    "scanned": {
        "title": "Scanned image-only pack (OCR path)",
        "description": "Full pack rendered as image-only PDFs — no text layer. Expect unknown/empty extract until local OCR exists.",
        "expected_rules": [],
        "mode": "scanned",
        "files": {
            "purchase_order_scan.pdf": _lines(
                "PURCHASE ORDER",
                "PO Number: PO-SCAN1",
                "Vendor: Scan Test Co",
                "Date: 11 January 2026",
                "Amount: PKR 90,000",
                "Description: Scanned stationery",
                "Approved by: Scan Buyer",
            ),
            "invoice_scan.pdf": _lines(
                "INVOICE",
                "Invoice ID: INV-SCAN1",
                "Vendor: Scan Test Co",
                "Invoice date: 18 January 2026",
                "PO Reference: PO-SCAN1",
                "Description: Scanned stationery",
                "Approval status: Approved",
                "Amount: PKR 90,000",
                "Tax: PKR 0",
            ),
            "payment_scan.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-SCAN1",
                "Vendor: Scan Test Co",
                "Date: 25 January 2026",
                "Amount: PKR 90,000",
                "Reference: INV-SCAN1",
            ),
            "approval_policy_scan.pdf": _lines(
                "APPROVAL POLICY",
                "Policy name: Scan Test Policy",
                "Spending limit: PKR 150,000",
                "Approval required above: PKR 150,000",
            ),
        },
        "images": {
            "invoice_scan.png": "\n".join(
                [
                    "INVOICE",
                    "Invoice ID: INV-SCAN1",
                    "Vendor: Scan Test Co",
                    "Invoice date: 18 January 2026",
                    "PO Reference: PO-SCAN1",
                    "Description: Scanned stationery",
                    "Approval status: Approved",
                    "Amount: PKR 90,000",
                    "Tax: PKR 0",
                ]
            ),
            "purchase_order_scan.png": "\n".join(
                [
                    "PURCHASE ORDER",
                    "PO Number: PO-SCAN1",
                    "Vendor: Scan Test Co",
                    "Date: 11 January 2026",
                    "Amount: PKR 90,000",
                    "Description: Scanned stationery",
                    "Approved by: Scan Buyer",
                ]
            ),
            "payment_scan.png": "\n".join(
                [
                    "PAYMENT RECORD",
                    "Payment ID: PAY-SCAN1",
                    "Vendor: Scan Test Co",
                    "Date: 25 January 2026",
                    "Amount: PKR 90,000",
                    "Reference: INV-SCAN1",
                ]
            ),
            "receipt_photo.png": "\n".join(
                [
                    "PAYMENT RECEIPT PHOTO",
                    "Vendor: Scan Test Co",
                    "Paid: PKR 90,000",
                    "Date: 25 January 2026",
                    "This PNG is for OCR tooling; the web uploader expects PDF today.",
                ]
            ),
        },
    },
    "hybrid": {
        "title": "Hybrid text + scanned invoice",
        "description": "Text PO/payment/policy with an image-only invoice. Tests mixed evidence quality.",
        "expected_rules": [],
        "files": {
            "purchase_order.pdf": _lines(
                "PURCHASE ORDER",
                "PO Number: PO-HY1",
                "Vendor: Hybrid Goods",
                "Date: 04 February 2026",
                "Amount: PKR 55,000",
                "Description: Hybrid pack",
                "Approved by: Hybrid Buyer",
            ),
            "payment.pdf": _lines(
                "PAYMENT RECORD",
                "Payment ID: PAY-HY1",
                "Vendor: Hybrid Goods",
                "Date: 20 February 2026",
                "Amount: PKR 55,000",
                "Reference: INV-HY1",
            ),
            "approval_policy.pdf": _lines(
                "APPROVAL POLICY",
                "Policy name: Hybrid Policy",
                "Spending limit: PKR 80,000",
                "Approval required above: PKR 80,000",
            ),
        },
        "scanned_files": {
            "invoice_scanned.pdf": _lines(
                "INVOICE",
                "Invoice ID: INV-HY1",
                "Vendor: Hybrid Goods",
                "Invoice date: 12 February 2026",
                "PO Reference: PO-HY1",
                "Description: Hybrid pack",
                "Approval status: Approved",
                "Amount: PKR 55,000",
                "Tax: PKR 0",
            ),
        },
        "images": {
            "invoice_scanned.png": "\n".join(
                [
                    "INVOICE",
                    "Invoice ID: INV-HY1",
                    "Vendor: Hybrid Goods",
                    "Invoice date: 12 February 2026",
                    "PO Reference: PO-HY1",
                    "Amount: PKR 55,000",
                    "Approval status: Approved",
                ]
            ),
        },
    },
    "noise": {
        "title": "Noise + unknown docs",
        "description": "Internal memo plus open-source PDF fixtures. Scope incomplete.",
        "expected_rules": [],
        "files": {
            "internal_memo.pdf": _lines(
                "INTERNAL MEMO",
                "To: Audit team",
                "From: Operations",
                "Subject: Parking note for Q3",
                "This note is not a purchase order, invoice, payment, or policy.",
                "Use it to confirm unknown classification.",
            ),
            "credit_note_lookalike.pdf": _lines(
                "CREDIT NOTE",
                "CN-778",
                "Vendor: Lookalike Ltd",
                "This is intentionally not in the classifier vocabulary.",
            ),
        },
        "external": ["tracemonkey.pdf"],
        "scanned_files": {
            "whiteboard_photo.pdf": _lines(
                "TEAM WHITEBOARD PHOTO",
                "Parking lot items only",
                "Not a purchase order or invoice",
                "Used as an OCR noise image inside a PDF wrapper",
            ),
        },
        "images": {
            "whiteboard_photo.png": "\n".join(
                [
                    "TEAM WHITEBOARD PHOTO",
                    "Parking lot items only",
                    "Not a purchase order or invoice",
                ]
            ),
        },
    },
}


def download_external(destination: Path, name: str, url: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = destination / name
    if target.is_file() and target.stat().st_size > 500:
        print(f"keep {target}")
        return
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            target.write_bytes(response.read())
        print(f"downloaded {target}")
    except Exception as exc:  # noqa: BLE001 — offline-friendly sample build
        print(f"skip {name} download ({exc})")
        write_sample_pdf(
            target,
            _lines(
                "OPEN SOURCE STAND-IN",
                f"Could not download {name}.",
                "This placeholder is still not a procurement document.",
            ),
        )
        print(f"wrote fallback {target}")


def write_pack(root: Path, pack_id: str, pack: dict) -> list[str]:
    folder = root / pack_id
    folder.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    mode = pack.get("mode", "text")
    writer = write_scanned_pdf if mode == "scanned" else write_sample_pdf

    for name, pages in pack.get("files", {}).items():
        path = folder / name
        writer(path, pages)
        written.append(str(path))
        print(path)

    for name, pages in pack.get("scanned_files", {}).items():
        path = folder / name
        write_scanned_pdf(path, pages)
        written.append(str(path))
        print(path)

    images_dir = root / "images" / pack_id
    for name, text in pack.get("images", {}).items():
        path = images_dir / name
        write_scan_png(path, text)
        print(path)

    for name in pack.get("external", []):
        src = root / "external" / name
        if src.is_file():
            target = folder / name
            target.write_bytes(src.read_bytes())
            written.append(str(target))
            print(target)

    meta = {
        "id": pack_id,
        "title": pack["title"],
        "description": pack["description"],
        "expected_rules": pack["expected_rules"],
        "mode": mode,
        "files": [Path(path).name for path in written],
        "images": list(pack.get("images", {}).keys()),
    }
    (folder / "pack.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return written


def sync_default_root(root: Path) -> None:
    """Keep samples/*.pdf as the mismatch pack for older callers and tests."""
    mismatch = PACKS["mismatch"]["files"]
    for name, pages in mismatch.items():
        path = root / name
        write_sample_pdf(path, pages)
        print(path)


def main() -> None:
    destination = samples_dir()
    destination.mkdir(parents=True, exist_ok=True)
    for name, url in EXTERNAL_FIXTURES.items():
        download_external(destination / "external", name, url)
    sync_default_root(destination)
    catalog = []
    for pack_id, pack in PACKS.items():
        written = write_pack(destination, pack_id, pack)
        catalog.append(
            {
                "id": pack_id,
                "title": pack["title"],
                "description": pack["description"],
                "expected_rules": pack["expected_rules"],
                "file_count": len(written),
                "image_count": len(pack.get("images", {})),
                "mode": pack.get("mode", "text"),
            }
        )
    (destination / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    readme = destination / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Sample document packs",
                "",
                "All packs under this folder are **synthetic** or open-source test fixtures.",
                "Do not add real invoices, payroll, or customer data here.",
                "",
                "Regenerate with:",
                "",
                "```bash",
                "cd audit_ai/backend",
                "python scripts/generate_samples.py",
                "```",
                "",
                "Packs:",
                "",
                *[
                    f"- `{item['id']}` — {item['title']}. {item['description']}"
                    + (f" ({item['image_count']} PNG scans in `images/{item['id']}/`)" if item.get("image_count") else "")
                    for item in catalog
                ],
                "",
                "## OCR / scanned fixtures",
                "",
                "- `scanned/` — image-only PDFs (no text layer).",
                "- `hybrid/` — text docs plus one scanned invoice PDF.",
                "- `images/<pack>/` — PNG scans for offline OCR experiments.",
                "- The prototype uploader accepts PDF today; PNGs are for OCR tooling beside the app.",
                "",
                "`external/` holds Mozilla pdf.js open-source fixtures used as unknown noise.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(readme)


if __name__ == "__main__":
    main()
