import os, pathlib
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/enrich")
DAILY_QUOTA = int(os.getenv("DAILY_QUOTA", "10"))

pool = ConnectionPool(DATABASE_URL, min_size=2, max_size=20, timeout=30,
                      kwargs={"row_factory": dict_row}, open=False)

def init_db():
    pool.open(wait=True)
    schema = (pathlib.Path(__file__).parent / "schema.sql").read_text()
    with pool.connection() as conn:
        conn.execute(schema)
        conn.execute("INSERT INTO quota (id, total) VALUES (1, %s) ON CONFLICT DO NOTHING", (DAILY_QUOTA,))
