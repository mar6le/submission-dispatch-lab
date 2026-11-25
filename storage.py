import sqlite3
from contextlib import closing
from pathlib import Path


class Submissions:
    def __init__(self, file):
        self.file = Path(file)
        self.file.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY,
                    group_code TEXT NOT NULL,
                    submission_key TEXT UNIQUE NOT NULL
                )
            """)

    def connect(self):
        db = sqlite3.connect(self.file, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def save(self, group, key):
        with closing(self.connect()) as db, db:
            written = db.execute(
                """INSERT INTO submissions (group_code, submission_key)
                   VALUES (?, ?) ON CONFLICT (submission_key) DO NOTHING""",
                (group, key),
            ).rowcount
            stored = db.execute(
                "SELECT id, group_code FROM submissions WHERE submission_key = ?", (key,)
            ).fetchone()
        return stored["id"], stored["group_code"], written == 1

    def find(self, number):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT id, group_code, submission_key FROM submissions WHERE id = ?", (number,)
            ).fetchone()
        return dict(row) if row else None
