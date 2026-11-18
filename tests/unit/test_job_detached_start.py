import queue
import subprocess
import sys

import pytest

from campfire_cli.app.job.service import detached_runner
from campfire_cli.common.exceptions import JobError


def test_startup_timeout_stops_worker_before_closing_its_blocked_pipe(tmp_path, monkeypatch):
    original_popen = subprocess.Popen
    original_queue = queue.Queue
    workers = []

    def spawn(command, **kwargs):
        worker = original_popen([sys.executable, "-c", "import time;time.sleep(60)"], **kwargs)
        workers.append(worker)
        return worker

    class ShortDeadlineQueue(original_queue):
        def get(self, block=True, timeout=None):
            return super().get(block, 0.05)

    monkeypatch.setattr(detached_runner.subprocess, "Popen", spawn)
    monkeypatch.setattr(detached_runner.queue, "Queue", ShortDeadlineQueue)
    try:
        with pytest.raises(JobError, match="Runner did not confirm startup"):
            detached_runner.start_detached(tmp_path, "example", "preview")
        assert workers[0].poll() is not None
        assert workers[0].stdout.closed and workers[0].stdin.closed
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
            worker.wait(timeout=5)
