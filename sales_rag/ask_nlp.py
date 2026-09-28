# Turn a question into a SQL query on the Gold warehouse, then run it.
#   python ask_nlp.py "What was total revenue in 2020?"

#-- read the question from the command line --
import sys
as_json = "--json" in sys.argv[1:] #sys.argv = ["ask_nlp.py", "What was total revenue in 2020?", "--json"]
question = " ".join(arg for arg in sys.argv[1:] if arg != "--json").strip()
if not question:
    raise SystemExit('Usage: python ask_nlp.py "your question"')

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
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=api_key, temperature=0)

SCHEMA = """
dbo.dimcustomer_gold(CustomerID bigint, CustomerName varchar, Email varchar, First varchar, Last varchar)
dbo.dimdate_gold(OrderDate date, Day int, Month int, Year int, mmmyyyy varchar, yyyymm varchar)
dbo.dimproduct_gold(ItemID bigint, ItemName varchar, ItemInfo varchar)
dbo.factsales_gold(CustomerID bigint, ItemID bigint, OrderDate date, Quantity int, UnitPrice real, Tax real)
dbo.forecast_backtest_gold(Model varchar, Fold bigint, CutoffDate date, HorizonEnd date, Grain varchar, Periods bigint, MAE float, RMSE float, MAPE float, sMAPE float, WAPE float, AccuracyPct float, BiasPct float, R2 float, DirAccuracyPct float, DirPrecision float, DirRecall float, DirF1 float, TP bigint, FP bigint, TN bigint, FN bigint, IsChampion bit, ModelRunTS datetime2, RunMode varchar)
dbo.revenue_forecast_gold(ForecastDate date, HorizonDay bigint, ForecastRevenue float, ForecastLower float, ForecastUpper float, Year int, Month int, yyyymm varchar, mmmyyyy varchar, Model varchar, HistoryEndDate date, ModelRunTS datetime2, RunMode varchar)
dbo.revenue_forecast_history_gold(PeriodStart date, PeriodEnd date, yyyymm varchar, ForecastDays bigint, ForecastRevenue float, ForecastLower float, ForecastUpper float, Model varchar, HistoryEndDate date, ModelRunTS datetime2, MLflowRunId varchar, RunMode varchar)
dbo.revenue_monthly_gold(PeriodStart date, PeriodEnd date, ActualRevenue float, ActualDays bigint, ForecastRevenue float, ForecastLower float, ForecastUpper float, ForecastDays bigint, Year int, Month int, yyyymm varchar, mmmyyyy varchar, TotalRevenue float, RecordType varchar, Model varchar, HistoryEndDate date, ModelRunTS datetime2, MLflowRunId varchar, RunMode varchar)
dbo.revenue_weekly_gold(PeriodStart date, PeriodEnd date, ActualRevenue float, ActualDays bigint, ForecastRevenue float, ForecastLower float, ForecastUpper float, ForecastDays bigint, IsoYear bigint, IsoWeek bigint, YearWeek varchar, TotalRevenue float, RecordType varchar, Model varchar, HistoryEndDate date, ModelRunTS datetime2, RunMode varchar)
Revenue on a sale line is Quantity * UnitPrice + Tax.
Join factsales_gold to dimcustomer_gold on CustomerID, to dimproduct_gold on ItemID, and to dimdate_gold on OrderDate.
"""
PROMPT = """Write one T-SQL SELECT that answers the question.
Use only the tables and columns in the context.
Include TOP 50 unless the question asks for one number.
Give every selected expression an alias.
Return only the SQL, with no explanation.

Context:
{context}

Question:
{question}
"""
sql = llm.invoke(PROMPT.format(context=SCHEMA, question=question)).content.strip()
if sql.startswith("```"):
    lines = sql.splitlines() #.splitlines() splits the string into a list of lines, removing the newline characters.
    lines = lines[1:] #drops the first line, which is the opening ```sql of the code block.
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1] #drops the last line if it is the closing ``` of the code block.
    sql = "\n".join(lines).strip()
sql = sql.strip().rstrip(";") #drops any trailing semicolon, which pyodbc does not like.
if not sql.lower().lstrip().startswith("select"):
    raise SystemExit("The model did not return a SELECT:\n" + sql)

#-- sign in and run that query on the Gold SQL endpoint --
import struct
import pyodbc
from azure.identity import AzureCliCredential

try:
    token = AzureCliCredential().get_token("https://database.windows.net/.default").token
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
    token = json.loads(proc.stdout)["accessToken"]
encoded = token.encode("utf-16-le")
token_struct = struct.pack(f"<I{len(encoded)}s", len(encoded), encoded)
SQL_SERVER = (
    "wsw7jvfvolau5hwgzi4rno2o6u-muomuhpchq7erj73xl37ziuot4"
    ".datawarehouse.fabric.microsoft.com"
)
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={SQL_SERVER};"
    "DATABASE=Gold;",
    attrs_before={1256: token_struct}, #1256 is the ODBC constant SQL_COPT_SS_ACCESS_TOKEN. It tells the driver "authenticate with this token instead of a password"
)
try:
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description] #cols
    fetched = cursor.fetchall() #rows
finally:
    conn.close()

rows = [["" if value is None else str(value) for value in row] for row in fetched]
if as_json:
    import json
    print("---JSON---")
    print(json.dumps({"columns": columns, "rows": rows, "sql": sql}))
else:
    if not rows:
        print("The query returned no rows.")
    else:
        print(" | ".join(columns))
        for row in rows:
            print(" | ".join(row))
    print("\nSQL:")
    print(sql)