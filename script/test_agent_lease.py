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

    def test_active_claim_rejects_second_worker(self):
        self.assertEqual(agent_lease.claim(self.claim_args()), 0)
        self.assertEqual(
            agent_lease.claim(self.claim_args("run-b", "worker-b")),
            2,
        )

    def test_completed_claim_can_be_reclaimed(self):
        self.assertEqual(agent_lease.claim(self.claim_args()), 0)
        finish_args = Namespace(
            db=self.db,
            task_id="task-a",
            run_id="run-a",
            worker_id="worker-a",
            status="COMPLETED",
            result_sha="def456",
            tests="unit",
            evidence="unit",
            remaining_blockers=None,
            next_dependency="task-b",
        )
        self.assertEqual(agent_lease.finish(finish_args), 0)
        self.assertEqual(
            agent_lease.claim(self.claim_args("run-b", "worker-b")),
            0,
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


if __name__ == "__main__":
    unittest.main()
