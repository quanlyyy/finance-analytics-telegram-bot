"""Consistent SQLite backup, for use from a scheduled server job."""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from backend.config import DATABASE_URL

def main():
    if not DATABASE_URL.startswith('sqlite:///'):
        raise SystemExit('For PostgreSQL use pg_dump instead.')
    source=Path(DATABASE_URL.removeprefix('sqlite:///'))
    if not source.is_file():raise SystemExit('Database does not exist')
    directory=Path('data/backups');directory.mkdir(parents=True,exist_ok=True)
    target=directory/('finance-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.db')
    with sqlite3.connect(source) as src,sqlite3.connect(target) as dst:
        src.backup(dst)
        result=dst.execute('PRAGMA integrity_check').fetchone()[0]
    if result!='ok':raise SystemExit('Backup integrity check failed')
    print(f'Backup verified: {target}')

if __name__=='__main__':main()
