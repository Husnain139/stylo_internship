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

PDF and Word files in `backend/data/policies` are the live library. They are read in document order when the API starts: one passage for a short section, one passage for each table row (with the column headers repeated), and a transcription for a picture that contains words. Logos and the advance-salary login picture are not passages. A scan such as the travel policy is transcribed page by page.

Sign-up and sign-in each ask for email and password. The email must already be on the employee list, and the password is stored as a salted hash. Name, designation, and admin status are read from the employees table. The API does not write that table. Policies, Questions people asked, and Checks are shown only when that person is an admin. Adding a person later is a new row.

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

Open http://localhost:3000. Postgres must be running. The API reads `DATABASE_URL` and `OPENAI_API_KEY` from `.env`.
