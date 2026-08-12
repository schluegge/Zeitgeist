import sqlite3
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import agent_lease


class AgentLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Path(self.temp_dir.name) / "leases.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def claim_args(self, run_id="run-a", worker_id="worker-a"):
        return Namespace(
            db=self.db,
            task_id="task-a",
            run_id=run_id,
            worker_id=worker_id,
            branch=f"branch-{run_id}",
            worktree=f"worktree-{run_id}",
            base_branch="origin/main",
            base_sha="abc123",
            lease_minutes=30,
            recover_stale=False,
        )

    def finish_args(self, run_id="run-a", worker_id="worker-a"):
        return Namespace(
            db=self.db,
            task_id="task-a",
            run_id=run_id,
            worker_id=worker_id,
            status="COMPLETED",
            result_sha="def456",
            tests="unit",
            evidence="unit",
            remaining_blockers=None,
            next_dependency="task-b",
        )

    def test_active_claim_rejects_second_worker(self):
        self.assertEqual(agent_lease.claim(self.claim_args()), 0)
        self.assertEqual(
            agent_lease.claim(self.claim_args("run-b", "worker-b")),
            2,
        )

    def test_completed_claim_can_be_reclaimed_without_losing_history(self):
        self.assertEqual(agent_lease.claim(self.claim_args()), 0)
        self.assertEqual(agent_lease.finish(self.finish_args()), 0)
        self.assertEqual(
            agent_lease.claim(self.claim_args("run-b", "worker-b")),
            0,
        )
        connection = sqlite3.connect(self.db)
        rows = connection.execute(
            "SELECT run_id, status, result_sha, evidence FROM leases "
            "WHERE task_id='task-a' ORDER BY claimed_at"
        ).fetchall()
        connection.close()
        self.assertEqual(
            rows,
            [
                ("run-a", "COMPLETED", "def456", "unit"),
                ("run-b", "CLAIMED", None, None),
            ],
        )

    def test_heartbeat_requires_matching_owner(self):
        self.assertEqual(agent_lease.claim(self.claim_args()), 0)
        heartbeat_args = Namespace(
            db=self.db,
            task_id="task-a",
            run_id="run-a",
            worker_id="worker-b",
            lease_minutes=30,
        )
        self.assertEqual(agent_lease.heartbeat(heartbeat_args), 3)

    def test_legacy_schema_migrates_without_data_loss(self):
        connection = sqlite3.connect(self.db)
        connection.execute("""
            CREATE TABLE leases (
                task_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                claimed_at TEXT NOT NULL,
                lease_expires_at TEXT NOT NULL,
                branch TEXT NOT NULL,
                worktree TEXT NOT NULL,
                status TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL,
                base_branch TEXT,
                base_sha TEXT,
                result_sha TEXT,
                finished_at TEXT,
                tests TEXT,
                evidence TEXT,
                remaining_blockers TEXT,
                next_dependency TEXT
            )
        """)
        connection.execute(
            """INSERT INTO leases VALUES (
            'task-a','run-old','worker-old','2026-08-12T00:00:00+00:00',
            '2026-08-12T00:10:00+00:00','old-branch','old-worktree','COMPLETED',
            '2026-08-12T00:05:00+00:00','main','abc','def','2026-08-12T00:05:00+00:00',
            'pass','evidence',NULL,'next')"""
        )
        connection.commit()
        connection.close()

        migrated = agent_lease.connect(self.db)
        pk = [
            row[1]
            for row in sorted(migrated.execute("PRAGMA table_info(leases)"), key=lambda r: r[5])
            if row[5]
        ]
        row = migrated.execute(
            "SELECT run_id,status,result_sha,evidence FROM leases WHERE task_id='task-a'"
        ).fetchone()
        migrated.close()
        self.assertEqual(pk, ["task_id", "run_id"])
        self.assertEqual(row, ("run-old", "COMPLETED", "def", "evidence"))


if __name__ == "__main__":
    unittest.main()
