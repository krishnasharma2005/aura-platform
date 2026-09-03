"""Run the workflow scheduler from the command line.

The default deployment runs the scheduler *inside* the API process as an
asyncio task (see `src/workflows/runner.py` and the FastAPI lifespan in
`src/main.py`). This command is the alternative for anyone who would rather
cron owned the schedule:

    # one pass, then exit — put this on a */1 * * * * cron or a CronJob
    python -m scripts.run_workflows --once

    # or a long-lived loop, for a dedicated worker container
    python -m scripts.run_workflows

Set `WORKFLOWS_RUNNER_ENABLED=false` on the API when you use this, so the
schedule has one owner. Running both anyway is harmless — work is claimed with
a conditional UPDATE that advances the schedule in the same statement, so
nothing fires twice.
"""

import argparse
import asyncio
import sys

from src.core.config import get_settings
from src.workflows import runner


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run due AURA workflows.")
    parser.add_argument("--once", action="store_true", help="Run a single tick and exit.")
    args = parser.parse_args()

    if args.once:
        result = await runner.tick()
        print(f"Started {result['started']} scheduled run(s); advanced {result['advanced']} run(s).")
        return

    interval = get_settings().WORKFLOW_TICK_SECONDS
    print(f"Workflow runner {runner.WORKER_ID} started; ticking every {interval}s. Ctrl-C to stop.")
    while True:
        result = await runner.tick()
        if result["started"] or result["advanced"]:
            print(f"started={result['started']} advanced={result['advanced']}")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(0)
