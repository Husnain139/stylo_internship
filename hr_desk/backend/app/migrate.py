"""Run database schema changes explicitly before deploying the API."""

import os

from .store_pg import PostgresStore


def main() -> None:
    dsn = os.environ.get("HR_DESK_MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Set the target database for the migration.")
    store = PostgresStore(dsn, migrate=True)
    store.ping()
    store.conn.close()
    print("HR Desk schema is ready.")


if __name__ == "__main__":
    main()
