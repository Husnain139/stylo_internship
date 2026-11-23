# Stylo HR Desk

Employees can ask about Stylo policies, follow up in a private chat, and open the policy excerpts used in an answer. HR can manage people and review policy drafts before publishing them.

## Run HR Desk locally

From this directory in PowerShell, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-HRDesk.ps1
```

You need Docker Desktop, Node 22, Python, and an OpenAI API key in `.env`. HR Desk uses the local `hr_desk` PostgreSQL database on port 5433. The production Next.js build is served on [localhost:3000](http://localhost:3000).

On a fresh local database, or after a schema update, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-HRDesk.ps1 -Initialize
```

`-Initialize` applies the schema and loads the bundled reference policies once. Add `-SampleEmployees` when you want to seed the sample employee records. Normal startup uses the existing database and library.

### Sample accounts for local testing

For local testing, use **Set up your account**, enter one of these sample employee emails, and choose a password of at least 12 characters. If you already set a password, use **Sign in**.

- Intern ? `sara.intern@stylo.example`
- Officer ? `ali.employee@stylo.example`
- Senior Manager ? `ayesha.manager@stylo.example`
- Executive ? `omer.executive@stylo.example`
- HR administrator ? `insrah.hr@stylo.example`
- Assistant General Manager: `farah.agm@stylo.example`
- Deputy General Manager: `bilal.dgm@stylo.example`
- General Manager: `hina.gm@stylo.example`
- Store Manager: `amna.store@stylo.example`
- Area Sales Manager: `hamza.area@stylo.example`
- People Specialist: `zara.people@stylo.example`

`-SampleEmployees` refreshes these local accounts without resetting their passwords. This release uses designations printed in the policies, not the unpublished new-grade entitlement mappings. The employee chat shows answers and relevant form links. HR still sees evidence when reviewing policy drafts.

Ask **message from ceo** as Sara to check access to Code of Conduct. Ask **What is the fuel entitlement for SM / AGM?** as Sara and Ayesha to compare access. As Insrah, upload a policy on **Policies**, inspect the draft's passages and grades, then confirm and publish. A failed publication leaves the old policy live. **Restore earlier version** restores a prior revision and the access settings it had at that revision.

Direct password setup is available to sample employees when HR Desk runs on localhost. Company deployments use email verification.

Press Ctrl+C in the launch terminal to stop the app. If HR Desk is running detached, use `Stop-HRDesk.ps1`. To stop PostgreSQL:

```powershell
docker compose stop db
```

## Data and cost controls

- PostgreSQL and pgvector store document audiences, passage grade access, effective dates, embeddings, and the published version. Search applies these filters before ranking. HR reviews the suggested grade restrictions with the policy source.
- Employees can keep up to 20 chats, up to 40 messages per chat, for 30 days of inactivity. A follow-up uses at most six messages and about 1 KB of prior text. Scope changes and source expiry hide affected saved answers. Deleting a chat removes its transcript. HR's separate question log has three-month retention.
- An exact answer cache is scoped to role, library revision, model configuration, and date. It expires after one hour, is capped at 1,000 rows, and rechecks cited passages before returning an answer.
- Accounts can ask 20 questions per 15-minute period. Across the app, the limits are 120 per 15 minutes, 600 per day, four simultaneous questions, and up to 3,000 OpenAI calls per day including retries and indexed batches. Monitor actual spend through the company OpenAI project. The app's request caps are separate from vendor billing alerts.
- The office and pasted-text readers use a 3,200-byte passage cap with up to 400 bytes of natural-boundary overlap. Prompts have a separate evidence budget. PDF page images are reserved for HR because a single page can contain both permitted and restricted content.
- The current reference Travel and Medical PDFs use supplementary, version-pinned transcriptions. New PDFs use the text layer, table detection, and local Tesseract OCR when available. Check the review notes for images, scanned material, and anything that needs manual verification. Word evidence is shown as extracted text or embedded pictures. Full Word page previews require a pre-rendered source PDF for that revision.

## Publish or replace a policy

Upload a file or paste the policy text in **Policies**. HR Desk saves the upload as a PostgreSQL job and extracts it outside the upload request. **Document processing** shows queued, running, failed, and completed jobs. A failed job can be retried from the same screen. Unfinished jobs can be picked up again after an API restart.

Compare the draft against its source, especially OCR text, table rows, effective dates, and access. Confirm the review and publish to index the draft. A replacement with a future start date appears as **Scheduled**. The prior revision remains searchable through the day before the replacement starts. The app rejects a schedule that would leave a gap after the prior revision expires.

For local English OCR, set `TESSDATA_PREFIX` to the directory containing `eng.traineddata`. On Windows, the launcher also checks `.runtime/tessdata` for that file. [Tesseract English language data](https://github.com/tesseract-ocr/tessdata_fast/blob/main/eng.traineddata)

## Deploy on the company network

Have HR confirm the actual role and grade matrix and approve the documents that can be sent to the OpenAI API. Remove the sample employee records before enabling company access. Use a company HTTPS origin, a private backend and PostgreSQL service, verified company SMTP, real service credentials, and backups for the database and policy files.

1. Configure the API with the company values in `.env.example`, including the public HTTPS origin, company email domain, SMTP sender, PostgreSQL credentials, and the runtime data directory. Use an OpenAI project approved for policy data.
2. Run `python -m app.migrate` from `backend` with the migration account. Run the API with the restricted application account. The API reads the existing schema at startup.
3. Provision the first HR admin in `employees` with a real work email, name, `designation='hr'`, and `is_admin=true`. Leave `password_hash` empty so the admin can set a password through email verification. HR can add the rest of the employee records through **People** and publish approved documents through **Policies**.
4. Run the FastAPI service and the Next.js production build behind the company HTTPS proxy. Bind both services to loopback when the proxy runs on the same host, and keep PostgreSQL private. Configure request-size and timeout limits. Test restoring the database and policy files before inviting employees.

## Verify a change

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
cd ..\web
npm.cmd run typecheck
npm.cmd run build
```

The backend suite includes PostgreSQL integration when `HR_DESK_TEST_DATABASE_URL` points at a separate database whose name ends in `_test`. The admin Checks page runs offline question-rule and formatting checks. To run the live evaluation, set `HR_DESK_EVAL_EMPLOYEE_EMAIL` to an account authorized to read the summary report, then run `python -m evals` from `backend` against the intended database.
