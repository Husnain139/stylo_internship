# HR desk

Employees ask questions about Stylo policies. The answer comes only from the written policy, and each person only sees the policies for their role.

The screen is for employees and HR. It does not show models, scores, or internal ids.

## What it does

1. Check the question before any search. Pay for a named person, and requests to ignore the rules, stop here.
2. Reuse a saved answer when the same role asked something very similar, and the policies have not changed.
3. Search the policies that role is allowed to see. Search uses both meaning and the words in the question.
4. A short question with one clear policy uses `gpt-5-nano`. A comparison or a long question uses `gpt-5-mini`.
5. Remove invented links, chunk tags, and numbers that are not in the policy.
6. Save a trace HR can read in plain language.

PDF and Word files in `backend/data/policies` are loaded when the API starts. A file is skipped when its text cannot be read. Everyone can ask about the ones that loaded. The checks still use the separate sample policies in `backend/data/sample_policies`. The screen says the library is sample-only when those are the only policies loaded.

Access, until the company hierarchy is confirmed: an intern sees company-wide policies and intern policies. A manager sees company-wide policies and manager policies, not the intern handbook and not HR salary bands. HR can see and manage every policy. Practice sign-in uses five sample people. Company OAuth can later use the same email lookup.

## Run it

Postgres:

```powershell
cd hr_desk
docker compose up -d
copy .env.example .env
# Put OPENAI_API_KEY in .env
```

API:

```powershell
cd hr_desk\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m evals
uvicorn app.main:app --port 8000
```

`python -m evals` must pass before this is treated as ready. It exits with an error if the live check did not run.

Screen:

```powershell
cd hr_desk\web
npm install
npm run dev
```

Open http://localhost:3000.

Without Docker, set `HR_DESK_STORE=memory` in `.env` and leave `DATABASE_URL` empty. The same checks still run. Postgres is the store to use when Docker is available.
