# Turn a question into a SQL query on the Gold warehouse, then run it.
#   python ask_nlp.py "What was total revenue in 2020?"

#-- read .env --
from dotenv import load_dotenv
load_dotenv()

#-- ask Gemini --
import os
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from langchain_google_genai import ChatGoogleGenerativeAI
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise SystemExit("Set GOOGLE_API_KEY in .env")
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=api_key,
    temperature=0,
    thinking_budget=0,
)

SCHEMA = """
dbo.dimcustomer_gold(CustomerID bigint, CustomerName varchar, Email varchar, First varchar, Last varchar)
dbo.dimdate_gold(OrderDate date, Day int, Month int, Year int, mmmyyyy varchar, yyyymm varchar)
dbo.dimproduct_gold(ItemID bigint, ItemName varchar, ItemInfo varchar)
dbo.factsales_gold(CustomerID bigint, ItemID bigint, OrderDate date, Quantity int, UnitPrice real, Tax real)
dbo.forecast_backtest_gold(Model varchar, Fold bigint, CutoffDate date, HorizonEnd date, Grain varchar, Periods bigint, MAE float, RMSE float, MAPE float, sMAPE float, WAPE float, AccuracyPct float, BiasPct float, IsChampion bit, ModelRunTS datetime2, RunMode varchar)
dbo.revenue_forecast_gold(ForecastDate date, HorizonDay bigint, ForecastRevenue float, ForecastLower float, ForecastUpper float, Year int, Month int, yyyymm varchar, mmmyyyy varchar, Model varchar, HistoryEndDate date, ModelRunTS datetime2, RunMode varchar)
dbo.revenue_forecast_history_gold(PeriodStart date, PeriodEnd date, yyyymm varchar, ForecastDays bigint, ForecastRevenue float, ForecastLower float, ForecastUpper float, Model varchar, HistoryEndDate date, ModelRunTS datetime2, MLflowRunId varchar, RunMode varchar)
dbo.revenue_monthly_gold(PeriodStart date, PeriodEnd date, ActualRevenue float, ActualDays bigint, ForecastRevenue float, ForecastLower float, ForecastUpper float, ForecastDays bigint, Year int, Month int, yyyymm varchar, mmmyyyy varchar, TotalRevenue float, RecordType varchar, Model varchar, HistoryEndDate date, ModelRunTS datetime2, MLflowRunId varchar, RunMode varchar)
dbo.revenue_weekly_gold(PeriodStart date, PeriodEnd date, ActualRevenue float, ActualDays bigint, ForecastRevenue float, ForecastLower float, ForecastUpper float, ForecastDays bigint, IsoYear bigint, IsoWeek bigint, YearWeek varchar, TotalRevenue float, RecordType varchar, Model varchar, HistoryEndDate date, ModelRunTS datetime2, RunMode varchar)
Revenue on a sale line is Quantity * UnitPrice + Tax.
Join factsales_gold to dimcustomer_gold on CustomerID, to dimproduct_gold on ItemID, and to dimdate_gold on OrderDate.
"""
PROMPT = """Answer with two parts and nothing else.
First line, alone: chart: bar, line, pie, stacked, scatter, dot, bullet, box, correlation, or none.
Then one T-SQL query. It may start with SELECT or WITH.

Use chart: none when the question does not ask for a plot, chart, or graph.
Use only the tables and columns in the context.
Give every selected expression an alias.
Do not use OFFSET or FETCH. TOP and OFFSET cannot be in the same query.
Sales are SUM(Quantity * UnitPrice + Tax). Rank the most sold items by SUM(Quantity).
A quarter is Q1 for Month 1-3, Q2 for 4-6, Q3 for 7-9, and Q4 for 10-12.
When the question names dates, filter OrderDate, or Year and Month, or PeriodStart.

Pie: a label, then one number. Use TOP 8.
Simple bar: a label, then one number. Use TOP 50 unless the result is one number.
Grouped bar or a line with several lines: category or date, series name, number. At most four series.
Line or grouped bar over a year: group by month with mmmyyyy and Month, and order by Month.
Stacked bar: category, series name, number. For quarterly sales the category is the item, the series is Q1 Q2 Q3 Q4, and the number is sales. Keep the top 8 items in an inner TOP 8, not on the outer SELECT, so each item has all four quarters. Order items by total sales descending, then quarter.
Scatter: two numeric columns, x then y. An optional third column is a series name. Group by month or by item, not by order.
Dot: a category and one number. An optional third column is a series name. Use TOP 12.
Bullet: a label, the actual number, and the target number. ActualRevenue is on RecordType actual. ForecastRevenue is on RecordType forecast. Combine those rows by Year and Month so each label has both numbers. Use mmmyyyy as the label.
Box: a category and one daily sales value. For quarters, the category is Q1 Q2 Q3 Q4 and each row is one day's sales. At most 400 rows.
Correlation: one row per month and at least two numeric measure columns, such as quantity, sales, and tax. Do not return one row per order.

Context:
{context}

{history}Question:
{question}
"""
def sql_for(question, history=None):
    prior = ""
    if history:
        blocks = []
        for turn in history[-4:]:
            columns = ", ".join(turn.get("columns") or [])
            blocks.append(
                "Question: " + str(turn.get("question") or "") + "\n"
                "Columns: " + columns + "\n"
                "SQL:\n" + str(turn.get("sql") or "")
            )
        prior = (
            "Previous turns in this chat, oldest first. "
            "When the new question is a follow-up, change the latest SQL instead of starting over.\n"
            + "\n\n".join(blocks)
            + "\n\n"
        )
    text = llm.invoke(PROMPT.format(context=SCHEMA, history=prior, question=question)).content
    if not isinstance(text, str):
        text = "".join(getattr(part, "text", "") for part in text)
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()  # drops the opening ``` fence
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    chart = "none"
    sql = text
    charts = ("bar", "line", "pie", "stacked", "scatter", "dot", "bullet", "box", "correlation", "none")
    aliases = {"stack": "stacked", "stackedbar": "stacked", "boxplot": "box", "corr": "correlation"}
    if text.lower().startswith("chart:"):
        after = text.split(":", 1)[1].strip()
    else:
        after = text
    pieces = after.split(None, 1)
    kind = aliases.get(pieces[0].lower().strip(".,"), pieces[0].lower().strip(".,")) if pieces else ""
    if kind in charts:
        chart = kind
        sql = pieces[1].strip() if len(pieces) > 1 else ""
    sql = sql.strip().rstrip(";")  # pyodbc rejects a trailing semicolon
    head = sql.lower().lstrip()
    if not (head.startswith("select") or head.startswith("with")):
        raise SystemExit("The model did not return a SELECT:\n" + text)
    return chart, sql


#-- sign in once and reuse the Gold connection --
import struct
import threading
import time
import pyodbc
from azure.identity import AzureCliCredential

SQL_SERVER = (
    "wsw7jvfvolau5hwgzi4rno2o6u-muomuhpchq7erj73xl37ziuot4"
    ".datawarehouse.fabric.microsoft.com"
)
_lock = threading.Lock()
_token = None  # (access token, unix expiry)
_conn = None


def access_token():
    global _token
    now = time.time()
    if _token and now < _token[1] - 300:
        return _token[0]
    try:
        access = AzureCliCredential().get_token("https://database.windows.net/.default")
        _token = (access.token, access.expires_on)
        return access.token
    except Exception:
        # az.cmd fails when a proxy inspects TLS. The CLI's own Python can use the OS trust store.
        import subprocess
        cli_python = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe"
        site = os.path.dirname(os.path.dirname(truststore.__file__))
        script = (
            "import sys\n"
            f"sys.path.insert(0, {site!r})\n"
            "import truststore\n"
            "truststore.inject_into_ssl()\n"
            "from azure.cli.core import get_default_cli\n"
            "raise SystemExit(get_default_cli().invoke(["
            "'account','get-access-token','--resource','https://database.windows.net','-o','json']))\n"
        )
        proc = subprocess.run([cli_python, "-c", script], capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(proc.stderr or proc.stdout)
        import json
        payload = json.loads(proc.stdout)
        raw = str(payload.get("expiresOn") or payload.get("expires_on"))
        if raw.isdigit():
            expires = float(raw)
        else:
            expires = time.mktime(time.strptime(raw[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S"))
        _token = (payload["accessToken"], expires)
        return payload["accessToken"]


def connect():
    token = access_token()
    encoded = token.encode("utf-16-le")
    token_struct = struct.pack(f"<I{len(encoded)}s", len(encoded), encoded)
    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SQL_SERVER};"
        "DATABASE=Gold;",
        attrs_before={1256: token_struct},  # 1256 is SQL_COPT_SS_ACCESS_TOKEN
    )


def query_gold(sql):
    global _conn
    with _lock:
        for attempt in (1, 2):
            try:
                if _conn is None:
                    _conn = connect()
                cursor = _conn.cursor()
                cursor.execute(sql)
                columns = [col[0] for col in cursor.description]
                fetched = cursor.fetchall()
                break
            except Exception:
                if _conn is not None:
                    _conn.close()
                _conn = None
                if attempt == 2:
                    raise
        rows = [["" if value is None else str(value) for value in row] for row in fetched]
        return columns, rows


def run(question, history=None):
    chart, sql = sql_for(question, history)
    columns, rows = query_gold(sql)
    return {"chart": chart, "columns": columns, "rows": rows, "sql": sql}


if __name__ == "__main__":
    #-- read the question from the command line --
    import sys
    as_json = "--json" in sys.argv[1:]  # sys.argv = ["ask_nlp.py", "What was total revenue in 2020?", "--json"]
    question = " ".join(arg for arg in sys.argv[1:] if arg != "--json").strip()
    if not question:
        raise SystemExit('Usage: python ask_nlp.py "your question"')
    result = run(question)
    if as_json:
        import json
        print("---JSON---")
        print(json.dumps(result))
    else:
        if not result["rows"]:
            print("The query returned no rows.")
        else:
            print(" | ".join(result["columns"]))
            for row in result["rows"]:
                print(" | ".join(row))
        print("\nSQL:")
        print(result["sql"])