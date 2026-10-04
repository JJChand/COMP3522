"""Read credentials from the root .env without exposing their values."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]


def connect():
    import psycopg
    from dotenv import load_dotenv

    load_dotenv(ROOT / '.env', override=False, interpolate=False)
    names = ('PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD')
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise ValueError('Missing environment keys: ' + ', '.join(missing))
    return psycopg.connect(
        host=os.environ['PGHOST'], port=int(os.environ['PGPORT']),
        dbname=os.environ['PGDATABASE'], user=os.environ['PGUSER'],
        password=os.environ['PGPASSWORD'], connect_timeout=10,
        options='-c default_transaction_read_only=on -c statement_timeout=120000',
        application_name='comp3522_task1_analysis',
    )
