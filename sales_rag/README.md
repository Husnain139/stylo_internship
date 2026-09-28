# Sales RAG

Ask a question about the Gold warehouse. The script turns the question into one T-SQL SELECT and runs it on the Gold SQL endpoint. The rows are the result.

```
question → one prompt (schema as context) → SELECT
         → Gold SQL endpoint → rows
```

## How to run

```bash
cd sales_rag
pip install -r requirements.txt
cp .env.example .env    # set GOOGLE_API_KEY
az login
python ask_nlp.py "What was total revenue in 2020?"
```

Sign in with `az login` first. The SQL endpoint is the Gold mirrored warehouse.

## App

FastAPI runs `ask_nlp.py`. The Next.js page in `web/` is the form.

```bash
cd sales_rag
pip install -r requirements.txt
python -m uvicorn api:app --port 8000

cd web
npm install
npm run dev
```

Open http://localhost:3000.
