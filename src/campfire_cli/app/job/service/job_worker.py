"""Internal detached execution entry, sharing the ordinary JobService run path."""

import json
import sys

from campfire_cli.common.exceptions import AppError, JobError
from campfire_cli.container import AppContainer


def main() -> None:
    service = AppContainer.build_job()
    ready = False

    def started(run: dict) -> None:
        nonlocal ready
        print(json.dumps({"status": "ok", "run": run}), flush=True)
        ready = True
        if sys.stdin.readline() != "execute\n":
            raise JobError("start-cancelled", "Startup was not acknowledged")

    try:
        service.run(sys.argv[1], True, sys.argv[2], on_started=started)
    except AppError as exc:
        if not ready:
            print(json.dumps(exc.payload()), flush=True)
    finally:
        service.runs.close()


if __name__ == "__main__":
    main()
