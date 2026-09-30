"""Durable state for the Cloud worker.

The in-memory queue in ``CloudWorker`` stays the working set. This mirrors it to
a small SQLite file so a worker crash between "result produced" and "result
acknowledged by the Cloud API" does not lose command results or events, and it
remembers which commands already ran so a restarted worker never applies the
same command twice. Records never contain credentials (they are redacted before
they are queued), and the file is created owner-only. Delivery is at-least-once;
the API deduplicates on ``record_id``.
"""

import json
import os
import sqlite3
import threading


class Outbox:
    def __init__(self, path, executed_limit=5000):
        self.path = path
        self.executed_limit = executed_limit
        self.lock = threading.Lock()
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        if not os.path.exists(path):
            os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS outbox ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "record_id TEXT NOT NULL UNIQUE, body TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS executed ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "command_id TEXT NOT NULL UNIQUE, result TEXT NOT NULL)"
        )
        self.db.commit()

    def load(self, limit):
        with self.lock:
            rows = self.db.execute(
                "SELECT body FROM outbox ORDER BY seq LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(body) for (body,) in rows]

    def add(self, record):
        with self.lock:
            self.db.execute(
                "INSERT OR IGNORE INTO outbox (record_id, body) VALUES (?, ?)",
                (record["record_id"], json.dumps(record, sort_keys=True)),
            )
            self.db.commit()

    def remove(self, records):
        with self.lock:
            self.db.executemany(
                "DELETE FROM outbox WHERE record_id = ?",
                [(record["record_id"],) for record in records],
            )
            self.db.commit()

    def remember_result(self, command_id, result):
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO executed (command_id, result) VALUES (?, ?)",
                (command_id, json.dumps(result, sort_keys=True)),
            )
            self.db.execute(
                "DELETE FROM executed WHERE seq <= (SELECT MAX(seq) FROM executed) - ?",
                (self.executed_limit,),
            )
            self.db.commit()

    def recall_result(self, command_id):
        with self.lock:
            row = self.db.execute(
                "SELECT result FROM executed WHERE command_id = ?", (command_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def close(self):
        with self.lock:
            self.db.close()
