"""Load reference policies and optionally add sample employees for local testing."""

from argparse import ArgumentParser
from shutil import copyfile

from .activation import allows_local_password_setup
from .access import reference_audience
from .config import BACKEND_ROOT, DATA_ROOT
from .factory import build_pipeline, index_missing_policies
from .ingest import POLICY_DIR, load_office_policies

SAMPLE_EMPLOYEES = (
    ("sara.intern@stylo.example", "Sara", "intern", False),
    ("ali.employee@stylo.example", "Ali", "officer", False),
    ("ayesha.manager@stylo.example", "Ayesha", "senior_manager", False),
    ("omer.executive@stylo.example", "Omer", "executive", False),
    ("insrah.hr@stylo.example", "Insrah", "hr", True),
    ("farah.agm@stylo.example", "Farah", "assistant_general_manager", False),
    ("bilal.dgm@stylo.example", "Bilal", "deputy_general_manager", False),
    ("hina.gm@stylo.example", "Hina", "general_manager", False),
    ("amna.store@stylo.example", "Amna", "store_manager", False),
    ("hamza.area@stylo.example", "Hamza", "area_sales_manager", False),
    ("zara.people@stylo.example", "Zara", "people_specialist", False),
)


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--sample-employees", action="store_true")
    args = parser.parse_args()
    original = BACKEND_ROOT / "data"
    if not allows_local_password_setup() or DATA_ROOT == original.resolve():
        raise RuntimeError("Use Start-HRDesk.ps1 -Initialize to initialize the local library.")
    pipeline = build_pipeline()
    store = pipeline.store
    if args.sample_employees:
        for person in SAMPLE_EMPLOYEES:
            email, _, designation, is_admin = person
            if not store.create_employee(*person):
                existing = store.employee(email)
                if existing and (existing.designation, existing.is_admin) != (designation, is_admin):
                    store.update_employee(email, designation, is_admin)
    with store.conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS reference_library_initialized (initialized BOOLEAN PRIMARY KEY DEFAULT TRUE)")
        cur.execute("SELECT initialized FROM reference_library_initialized")
        initialized = cur.fetchone()
    if initialized:
        print("HR Desk database is ready.")
        return
    for folder in ("policies", "transcriptions"):
        destination = DATA_ROOT / folder
        destination.mkdir(parents=True, exist_ok=True)
        for source in (original / folder).iterdir():
            if source.is_file() and not (destination / source.name).exists():
                copyfile(source, destination / source.name)
    policies = load_office_policies()
    for policy in policies:
        policy.audience = reference_audience(policy.title)
    index_missing_policies(store, pipeline.embedder, policies)
    if not store.list_policies():
        raise RuntimeError(f"No reference policies were found in {POLICY_DIR}.")
    with store.conn.cursor() as cur:
        cur.execute("INSERT INTO reference_library_initialized DEFAULT VALUES ON CONFLICT DO NOTHING")
    print("HR Desk database is ready.")


if __name__ == "__main__":
    main()
