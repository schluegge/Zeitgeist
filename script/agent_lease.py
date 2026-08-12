from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

STATUSES = {"CLAIMED", "RUNNING", "BLOCKED", "COMPLETED", "ABANDONED"}
COLUMNS = (
    "task_id", "run_id", "worker_id", "claimed_at", "lease_expires_at",
    "branch", "worktree", "status", "heartbeat_at", "base_branch",
    "base_sha", "result_sha", "finished_at", "tests", "evidence",
    "remaining_blockers", "next_dependency",
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS leases (
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    claimed_at TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    branch TEXT NOT NULL,
    worktree TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('CLAIMED', 'RUNNING', 'BLOCKED', 'COMPLETED', 'ABANDONED')),
    heartbeat_at TEXT NOT NULL,
    base_branch TEXT,
    base_sha TEXT,
    result_sha TEXT,
    finished_at TEXT,
    tests TEXT,
    evidence TEXT,
    remaining_blockers TEXT,
    next_dependency TEXT,
    PRIMARY KEY (task_id, run_id)
)
"""


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.isoformat()


def ensure_schema(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='leases'"
    ).fetchone()
    if row is None:
        connection.execute(SCHEMA)
        return
    info = connection.execute("PRAGMA table_info(leases)").fetchall()
    primary_key = [
        item[1] for item in sorted(info, key=lambda item: item[5]) if item[5]
    ]
    if primary_key == ["task_id", "run_id"]:
        return
    if primary_key != ["task_id"]:
        raise RuntimeError(f"Unsupported leases primary key: {primary_key}")

    names = ", ".join(COLUMNS)
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("ALTER TABLE leases RENAME TO leases_legacy_v1")
        connection.execute(SCHEMA)
        connection.execute(
            f"INSERT INTO leases ({names}) SELECT {names} FROM leases_legacy_v1"
        )
        connection.execute("DROP TABLE leases_legacy_v1")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15, isolation_level=None)
    connection.execute("PRAGMA journal_mode=WAL")
    ensure_schema(connection)
    return connection


def get_latest_row(connection: sqlite3.Connection, task_id: str):
    connection.row_factory = sqlite3.Row
    return connection.execute(
        "SELECT * FROM leases WHERE task_id = ? ORDER BY claimed_at DESC LIMIT 1",
        (task_id,),
    ).fetchone()


def get_unfinished_row(connection: sqlite3.Connection, task_id: str):
    connection.row_factory = sqlite3.Row
    return connection.execute(
        """SELECT * FROM leases
        WHERE task_id = ? AND status IN ('CLAIMED', 'RUNNING')
        ORDER BY claimed_at DESC LIMIT 1""",
        (task_id,),
    ).fetchone()


def active(row, now: dt.datetime) -> bool:
    if row is None:
        return False
    return dt.datetime.fromisoformat(row["lease_expires_at"]) > now

def claim(args: argparse.Namespace) -> int:
    now = utcnow()
    expires = now + dt.timedelta(minutes=args.lease_minutes)
    connection = connect(args.db)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = get_unfinished_row(connection, args.task_id)
        if active(row, now):
            print(json.dumps(dict(row), indent=2))
            connection.execute("ROLLBACK")
            return 2
        if row is not None and not args.recover_stale:
            print(json.dumps(dict(row), indent=2))
            connection.execute("ROLLBACK")
            return 4
        existing = connection.execute(
            "SELECT 1 FROM leases WHERE task_id=? AND run_id=?",
            (args.task_id, args.run_id),
        ).fetchone()
        if existing is not None:
            connection.execute("ROLLBACK")
            return 5
        connection.execute(
            """INSERT INTO leases
            (task_id, run_id, worker_id, claimed_at, lease_expires_at, branch,
             worktree, status, heartbeat_at, base_branch, base_sha)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'CLAIMED', ?, ?, ?)""",
            (args.task_id, args.run_id, args.worker_id, iso(now), iso(expires),
             args.branch, args.worktree, iso(now), args.base_branch, args.base_sha),
        )
        connection.execute("COMMIT")
        print(json.dumps(dict(get_latest_row(connection, args.task_id)), indent=2))
        return 0
    finally:
        connection.close()


def heartbeat(args: argparse.Namespace) -> int:
    now = utcnow()
    expires = now + dt.timedelta(minutes=args.lease_minutes)
    connection = connect(args.db)
    cursor = connection.execute(
        """UPDATE leases SET status='RUNNING', heartbeat_at=?, lease_expires_at=?
        WHERE task_id=? AND run_id=? AND worker_id=?""",
        (iso(now), iso(expires), args.task_id, args.run_id, args.worker_id),
    )
    connection.close()
    return 0 if cursor.rowcount == 1 else 3


def finish(args: argparse.Namespace) -> int:
    if args.status not in {"BLOCKED", "COMPLETED", "ABANDONED"}:
        raise SystemExit("finish status must be BLOCKED, COMPLETED, or ABANDONED")
    now = utcnow()
    connection = connect(args.db)
    cursor = connection.execute(
        """UPDATE leases SET status=?, heartbeat_at=?, lease_expires_at=?,
        finished_at=?, result_sha=?, tests=?, evidence=?, remaining_blockers=?,
        next_dependency=? WHERE task_id=? AND run_id=? AND worker_id=?""",
        (args.status, iso(now), iso(now), iso(now), args.result_sha, args.tests,
         args.evidence, args.remaining_blockers, args.next_dependency,
         args.task_id, args.run_id, args.worker_id),
    )
    connection.close()
    return 0 if cursor.rowcount == 1 else 3


def list_rows(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT * FROM leases ORDER BY claimed_at DESC"
    ).fetchall()
    print(json.dumps([dict(row) for row in rows], indent=2))
    connection.close()
    return 0


def add_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--worker-id", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    claim_parser = subparsers.add_parser("claim")
    add_identity(claim_parser)
    claim_parser.add_argument("--branch", required=True)
    claim_parser.add_argument("--worktree", required=True)
    claim_parser.add_argument("--base-branch", required=True)
    claim_parser.add_argument("--base-sha")
    claim_parser.add_argument("--lease-minutes", type=int, default=120)
    claim_parser.add_argument("--recover-stale", action="store_true")
    claim_parser.set_defaults(function=claim)

    heartbeat_parser = subparsers.add_parser("heartbeat")
    add_identity(heartbeat_parser)
    heartbeat_parser.add_argument("--lease-minutes", type=int, default=120)
    heartbeat_parser.set_defaults(function=heartbeat)

    finish_parser = subparsers.add_parser("finish")
    add_identity(finish_parser)
    finish_parser.add_argument("--status", required=True)
    finish_parser.add_argument("--result-sha")
    finish_parser.add_argument("--tests")
    finish_parser.add_argument("--evidence")
    finish_parser.add_argument("--remaining-blockers")
    finish_parser.add_argument("--next-dependency")
    finish_parser.set_defaults(function=finish)

    list_parser = subparsers.add_parser("list")
    list_parser.set_defaults(function=list_rows)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.function(args)


if __name__ == "__main__":
    raise SystemExit(main())
