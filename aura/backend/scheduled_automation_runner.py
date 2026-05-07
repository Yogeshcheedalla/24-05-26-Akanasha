import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from .automation import execute_desktop_command


def _load_payload(path_arg: str) -> dict:
    payload_path = Path(path_arg)
    return json.loads(payload_path.read_text(encoding="utf-8"))


def _sleep_until(run_at_iso: str) -> None:
    target = datetime.fromisoformat(run_at_iso)
    if target.tzinfo is None:
        target = target.astimezone()
    while True:
        now = datetime.now(target.tzinfo)
        delay = (target - now).total_seconds()
        if delay <= 0:
            return
        time.sleep(min(delay, 30))


async def _run_plan(plan: dict) -> None:
    for step in plan.get("steps", []):
        result = await execute_desktop_command(
            step["action"],
            step.get("target"),
            step.get("payload"),
        )
        if not result.get("success"):
            break


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    payload = _load_payload(sys.argv[1])
    _sleep_until(payload["run_at"])
    asyncio.run(_run_plan(payload["plan"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
