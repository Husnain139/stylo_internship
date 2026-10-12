"""
Reject MRs in Dynamics 365 F&O via Playwright (Workflow work list).

Per MR (codegen):
  tick row checkbox -> Workflow -> Reject -> Reject

--all walks visible data-row checkboxes by offset.
On D365 error: do NOT close banners / Escape — just move to the next row.

Login stays manual. Do NOT put passwords in this file.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError, Page, expect, sync_playwright

DEFAULT_START_URL = (
    "https://enigmaaxis.sandbox.operations.eu.dynamics.com/"
    "?cmp=STL&mi=WorkflowWorkListAssignedToMe"
)

ACTION_TIMEOUT_MS = 15000
GONE_TIMEOUT_MS = 20000
SETTLE_MS = 2000
MAX_UI_FAILS_IN_A_ROW = 8

MR_IN_TEXT = re.compile(r"(MR-\d+)", re.IGNORECASE)
D365_ERRORS = (
    re.compile(r"Object reference not set to an instance of an object", re.I),
    re.compile(r"User\s*\{[0-9A-Fa-f-]+\}\s*not found", re.I),
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reject Dynamics 365 MRs via Workflow -> Reject.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true", help="Reject every MR shown in the list.")
    mode.add_argument("--ids", type=str, help="Comma-separated MR numbers.")
    mode.add_argument("--ids-file", type=Path, help="Text file, one MR number per line.")
    p.add_argument("--dry-run", action="store_true", help="Show targets; click nothing.")
    p.add_argument("--limit", type=int, default=0, help="Stop after N rejects (0 = no limit).")
    p.add_argument("--start-url", type=str, default=DEFAULT_START_URL, help="Work list URL.")
    p.add_argument("--comment", type=str, default="", help="Optional reject comment.")
    return p


def read_ids(args: argparse.Namespace) -> list[str]:
    if args.ids:
        raw = args.ids.split(",")
    elif args.ids_file:
        lines = args.ids_file.read_text(encoding="utf-8").splitlines()
        raw = [line for line in lines if not line.strip().startswith("#")]
    else:
        raw = []
    return [part.strip().upper() for part in raw if part.strip()]


def pause(prompt: str) -> None:
    try:
        input(prompt)
    except EOFError:
        pass


def ctx_text(ctx: Any) -> str:
    try:
        return ctx.locator("body").inner_text(timeout=5000) or ""
    except PlaywrightError:
        return ""


def listed_mr_ids(ctx: Any) -> list[str]:
    return list(dict.fromkeys(m.upper() for m in MR_IN_TEXT.findall(ctx_text(ctx))))


def resolve_ctx(page: Page) -> Any:
    """
    Use main page, or an iframe that actually contains the work list.
    (Escape spam previously wiped the list; iframes can also hide rows from page.*)
    """
    main = ctx_text(page)
    if "Document type" in main or listed_mr_ids(page) or page.get_by_role("row").count() > 0:
        return page
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            text = frame.locator("body").inner_text(timeout=2000) or ""
        except PlaywrightError:
            continue
        if "Document type" in text or MR_IN_TEXT.search(text) or "Work items" in text:
            print(f"  using iframe: {frame.url[:80]}")
            return frame
    return page


def is_header_row_text(text: str) -> bool:
    return bool(
        text
        and "Document type" in text
        and "Subject" in text
        and not MR_IN_TEXT.search(text)
    )


def data_checkbox_row_indexes(ctx: Any) -> list[int]:
    rows = ctx.get_by_role("row")
    indexes: list[int] = []
    n = rows.count()
    for i in range(n):
        row = rows.nth(i)
        try:
            text = (row.inner_text(timeout=1500) or "").strip()
            cbs = row.get_by_role("checkbox").count()
            if cbs == 0:
                cbs = row.locator('[role="checkbox"], input[type="checkbox"]').count()
        except PlaywrightError:
            continue
        if cbs == 0 or is_header_row_text(text):
            continue
        indexes.append(i)
    return indexes


def probe(page: Page, ctx: Any) -> None:
    print(f"  probe url: {page.url}")
    print(f"  probe frames: {len(page.frames)}")
    try:
        rows = ctx.get_by_role("row").count()
        cbs = ctx.get_by_role("checkbox").count()
    except PlaywrightError:
        rows, cbs = -1, -1
    print(f"  probe role=row: {rows}, role=checkbox: {cbs}")
    text = ctx_text(ctx)
    print(f"  probe MR ids: {listed_mr_ids(ctx)[:15]}")
    print(f"  probe has 'Document type': {'Document type' in text}")
    print(f"  probe body snippet: {text[:180]!r}")


def wait_for_rows(page: Page) -> tuple[Any, list[int]]:
    """Retry a few seconds — do NOT press Escape (that clears the F&O list)."""
    ctx = resolve_ctx(page)
    for attempt in range(10):
        indexes = data_checkbox_row_indexes(ctx)
        if indexes:
            return ctx, indexes
        if attempt == 0:
            print("  waiting for grid rows...")
        page.wait_for_timeout(1000)
        ctx = resolve_ctx(page)
    return ctx, []


def d365_error(ctx: Any) -> str:
    text = ctx_text(ctx)
    for pattern in D365_ERRORS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return ""


def fill_comment(ctx: Any, comment: str) -> None:
    for box in (ctx.locator("textarea").last, ctx.get_by_role("textbox").last):
        try:
            if box.count() and box.is_visible():
                box.fill(comment, timeout=ACTION_TIMEOUT_MS)
                return
        except PlaywrightError:
            continue


def guess_mr_label(ctx: Any, offset: int) -> str:
    ids = listed_mr_ids(ctx)
    if len(ids) > offset:
        return ids[offset]
    return f"(visible-row {offset + 1})"


def select_data_row(ctx: Any, offset: int) -> bool:
    indexes = data_checkbox_row_indexes(ctx)
    if offset < 0 or offset >= len(indexes):
        return False
    row = ctx.get_by_role("row").nth(indexes[offset])
    try:
        row.scroll_into_view_if_needed(timeout=5000)
        ctx.wait_for_timeout(200)
        row.click(timeout=ACTION_TIMEOUT_MS)
        ctx.wait_for_timeout(200)
        cb = row.get_by_role("checkbox").first
        if cb.count() == 0:
            cb = row.locator('[role="checkbox"], input[type="checkbox"]').first
        cb.click(timeout=ACTION_TIMEOUT_MS, force=True)
        ctx.wait_for_timeout(300)
        return True
    except PlaywrightError as exc:
        print(f"  checkbox click failed: {str(exc).split(chr(10), 1)[0]}")
        return False


def click_reject_ui(ctx: Any, comment: str) -> None:
    # Workflow lives on the shell; try ctx first, then fall back handled by caller page
    ctx.get_by_role("button", name=re.compile(r"^Workflow")).click(timeout=ACTION_TIMEOUT_MS)
    ctx.get_by_role("menuitem", name="Reject").click(timeout=ACTION_TIMEOUT_MS)
    confirm = ctx.get_by_role("button", name="Reject")
    confirm.wait_for(timeout=ACTION_TIMEOUT_MS)
    if comment:
        fill_comment(ctx, comment)
    confirm.click(timeout=ACTION_TIMEOUT_MS)
    expect(confirm).to_have_count(0, timeout=GONE_TIMEOUT_MS)


def click_reject_ui_page(page: Page, ctx: Any, comment: str) -> None:
    """Workflow button is usually on the main page chrome, not inside a nested frame."""
    targets = [page, ctx] if ctx is not page else [page]
    last_exc: Exception | None = None
    for target in targets:
        try:
            click_reject_ui(target, comment)
            return
        except (AssertionError, PlaywrightError) as exc:
            last_exc = exc
            continue
    raise last_exc or PlaywrightError("Reject UI failed")


def reject_by_offset(page: Page, ctx: Any, offset: int, comment: str) -> tuple[str, str, Any]:
    label = guess_mr_label(ctx, offset)
    indexes = data_checkbox_row_indexes(ctx)
    if offset >= len(indexes):
        print(f"  no data row at offset {offset} (visible={len(indexes)})")
        return "not_found", label, ctx

    before_count = len(indexes)
    if not select_data_row(ctx, offset):
        return "not_found", label, ctx

    reason = "still on list after Reject"
    try:
        click_reject_ui_page(page, ctx, comment)
        page.wait_for_timeout(SETTLE_MS)
        ctx = resolve_ctx(page)
        after_count = len(data_checkbox_row_indexes(ctx))
        gone = after_count < before_count
    except (AssertionError, PlaywrightError) as exc:
        gone = False
        reason = str(exc).split("\n", 1)[0] or "UI error"
        ctx = resolve_ctx(page)

    error = d365_error(page) or d365_error(ctx)
    if gone and not error:
        return "rejected", label, ctx

    print(f"  FAILED: {error or reason}")
    # Per user: do NOT close banner — just report and let caller bump offset
    return ("d365_error" if error else "failed"), label, ctx


def mr_row(ctx: Any, mr_id: str):
    return ctx.get_by_role("row", name=re.compile(rf"{re.escape(mr_id)}(?!\d)", re.I))


def reject_by_id(page: Page, mr_id: str, comment: str) -> str:
    ctx = resolve_ctx(page)
    row = mr_row(ctx, mr_id)
    if row.count() != 1:
        print(f"  {row.count()} rows match by name — cannot target {mr_id}")
        return "not_found"
    before = row.count()
    try:
        row.get_by_role("checkbox").first.click(timeout=ACTION_TIMEOUT_MS, force=True)
        click_reject_ui_page(page, ctx, comment)
        page.wait_for_timeout(SETTLE_MS)
        ctx = resolve_ctx(page)
        error = d365_error(page) or d365_error(ctx)
        gone = mr_row(ctx, mr_id).count() < before
        if gone and not error:
            return "rejected"
        print(f"  FAILED: {error or 'still listed after Reject'}")
        return "d365_error" if error else "failed"
    except (AssertionError, PlaywrightError) as exc:
        error = d365_error(page)
        print(f"  FAILED: {error or str(exc).split(chr(10), 1)[0]}")
        return "d365_error" if error else "failed"


def run_all(page: Page, args: argparse.Namespace) -> None:
    results: dict[str, list[str]] = {
        "rejected": [],
        "d365_error": [],
        "failed": [],
        "not_found": [],
    }
    ui_fails = 0
    row_offset = 0
    attempts = 0

    ctx, visible = wait_for_rows(page)
    print(f"Visible data checkbox rows: {len(visible)}")
    print(f"MR ids currently in page text: {listed_mr_ids(ctx)[:12]}")
    if not visible:
        probe(page, ctx)
        print("No data checkbox rows found. Is the work list grid focused in the Playwright window?")
        print("Summary: " + ", ".join(f"{k}={len(v)}" for k, v in results.items()))
        return

    while True:
        if args.limit and len(results["rejected"]) >= args.limit:
            print(f"Reached --limit {args.limit}. Stopping.")
            break

        ctx = resolve_ctx(page)
        indexes = data_checkbox_row_indexes(ctx)
        if not indexes:
            page.wait_for_timeout(1500)
            ctx, indexes = wait_for_rows(page)
        if not indexes:
            print("No data checkbox rows left. Done.")
            break

        if row_offset >= len(indexes):
            # Virtualized grid: only a few rows exist in the DOM. After skipping
            # broken ones, scroll to load more instead of stopping.
            print(
                f"  all {len(indexes)} visible row(s) skipped — scrolling for more..."
            )
            try:
                if indexes:
                    ctx.get_by_role("row").nth(indexes[-1]).click(timeout=5000)
                page.keyboard.press("PageDown")
                page.wait_for_timeout(800)
                page.keyboard.press("PageDown")
                page.wait_for_timeout(800)
            except PlaywrightError:
                pass
            ctx = resolve_ctx(page)
            new_indexes = data_checkbox_row_indexes(ctx)
            if not new_indexes or new_indexes == indexes:
                print(
                    f"No more rows loaded. "
                    f"rejected={len(results['rejected'])} "
                    f"d365_error={len(results['d365_error'])}. Stopping."
                )
                break
            row_offset = 0
            print(f"  now visible data rows: {len(new_indexes)}")
            continue

        attempts += 1
        label = guess_mr_label(ctx, row_offset)
        print(
            f"[{attempts}] REJECT {label} "
            f"(offset {row_offset}/{len(indexes) - 1}, rows visible={len(indexes)})"
        )

        if args.dry_run:
            print("  dry-run: would tick checkbox → Workflow → Reject")
            results["rejected"].append(label)
            break

        outcome, label, ctx = reject_by_offset(page, ctx, row_offset, args.comment)
        results[outcome].append(label)

        if outcome == "rejected":
            print(f"  rejected ({len(results['rejected'])} so far)")
            row_offset = 0
            ui_fails = 0
            page.wait_for_timeout(800)
        elif outcome == "d365_error":
            print("  skipped D365 error — next MR (banner left alone)")
            row_offset += 1
            ui_fails = 0
            page.wait_for_timeout(500)
        else:
            print("  failed — next MR")
            row_offset += 1
            ui_fails += 1

        if ui_fails >= MAX_UI_FAILS_IN_A_ROW:
            print(f"{MAX_UI_FAILS_IN_A_ROW} UI failures in a row. Stopping.")
            break

    print("Summary: " + ", ".join(f"{k}={len(v)}" for k, v in results.items()))
    for key in ("d365_error", "failed", "not_found"):
        if results[key]:
            print(f"  {key}: {', '.join(results[key])}")


def run_selected(page: Page, args: argparse.Namespace, ids: list[str]) -> None:
    results: dict[str, list[str]] = {
        "rejected": [],
        "d365_error": [],
        "failed": [],
        "not_found": [],
    }
    ui_fails = 0
    for i, mr_id in enumerate(ids, start=1):
        if args.limit and len(results["rejected"]) >= args.limit:
            print(f"Reached --limit {args.limit}. Stopping.")
            break
        print(f"[{i}/{len(ids)}] REJECT {mr_id}")
        if args.dry_run:
            ctx = resolve_ctx(page)
            print(f"  dry-run: name-match rows={mr_row(ctx, mr_id).count()}")
            continue
        outcome = reject_by_id(page, mr_id, args.comment)
        results[outcome].append(mr_id)
        if outcome == "rejected":
            print(f"  rejected ({len(results['rejected'])} so far)")
            ui_fails = 0
        elif outcome == "d365_error":
            print("  skipped D365 error — next MR (banner left alone)")
            ui_fails = 0
        else:
            ui_fails += 1
        if ui_fails >= MAX_UI_FAILS_IN_A_ROW:
            print(f"{MAX_UI_FAILS_IN_A_ROW} UI failures in a row. Stopping.")
            break

    print("Summary: " + ", ".join(f"{k}={len(v)}" for k, v in results.items()))
    for key in ("d365_error", "failed", "not_found"):
        if results[key]:
            print(f"  {key}: {', '.join(results[key])}")


def main() -> int:
    args = build_parser().parse_args()
    if args.ids_file and not args.ids_file.exists():
        print(f"File not found: {args.ids_file}", file=sys.stderr)
        return 1
    ids = read_ids(args)
    if not args.all and not ids:
        print("No MR IDs provided.", file=sys.stderr)
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_context().new_page()
        page.goto(args.start_url, wait_until="domcontentloaded")

        print("\nSign in and open the Workflow work list (Assigned to me)")
        print("in THIS Playwright Chromium window (not your normal Chrome).")
        pause("When MR rows are visible here, press Enter... ")

        if args.all:
            run_all(page, args)
        else:
            run_selected(page, args, ids)

        pause("Press Enter to close the browser... ")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
