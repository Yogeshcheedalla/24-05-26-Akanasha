from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, utc_now


class AutonomousTestingEngine:
    """Generates auditable test plans and records regression reports."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def generate_test_plan(
        self,
        scope: str,
        changed_files: list[str] | None = None,
        task: str = "",
    ) -> dict[str, Any]:
        changed_files = changed_files or []
        checks = ["unit_tests"]
        if any(path.endswith((".ts", ".tsx", ".js", ".jsx")) for path in changed_files):
            checks.extend(["type_check", "frontend_smoke"])
        if any("api" in path.replace("\\", "/") or "routes" in path for path in changed_files):
            checks.append("api_contract_tests")
        if any("database" in path.replace("\\", "/") or "store.py" in path for path in changed_files):
            checks.append("schema_integrity")
        if any("voice" in path.lower() or "avatar" in path.lower() for path in changed_files + [task]):
            checks.extend(["voice_state_machine", "avatar_silence_lock"])
        checks.append("regression_report")
        deduped = list(dict.fromkeys(checks))
        return {
            "scope": scope,
            "task": task,
            "changed_files": changed_files,
            "checks": deduped,
            "recommended_commands": self._commands(deduped),
            "confidence": self._confidence(deduped),
        }

    def record_report(
        self,
        scope: str,
        test_plan: dict[str, Any],
        command: str,
        status: str,
        output_summary: str,
        regressions: list[str] | None = None,
        performance_score: float | None = None,
    ) -> dict[str, Any]:
        if status not in {"passed", "failed", "partial"}:
            raise ValueError("Test status must be passed, failed, or partial")
        regressions = regressions or []
        score = performance_score if performance_score is not None else self._performance_score(status, regressions, output_summary)
        report_id = f"test_report_{uuid4().hex}"
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT INTO autonomous_test_reports(
                    id, scope, test_plan, command, status, output_summary,
                    regressions, performance_score, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    scope,
                    dumps(test_plan),
                    command,
                    status,
                    output_summary,
                    dumps(regressions),
                    round(max(0.0, min(1.0, float(score))), 3),
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM autonomous_test_reports WHERE id = ?", (report_id,)).fetchone()
        return self._decode(row)

    def compare_results(self, previous_report_id: str, current_report_id: str) -> dict[str, Any]:
        previous = self._get_report(previous_report_id)
        current = self._get_report(current_report_id)
        delta = round(float(current["performance_score"]) - float(previous["performance_score"]), 3)
        regressions = list(current["regressions"])
        if previous["status"] == "passed" and current["status"] != "passed":
            regressions.append("status_regressed_from_passed")
        return {
            "previous": previous_report_id,
            "current": current_report_id,
            "performance_delta": delta,
            "regressions": list(dict.fromkeys(regressions)),
            "improved": delta >= 0 and current["status"] == "passed",
        }

    def reports(self, scope: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        sql = "SELECT * FROM autonomous_test_reports"
        params: list[Any] = []
        if scope:
            sql += " WHERE scope = ?"
            params.append(scope)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 100)))
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._decode(row) for row in rows]

    def _commands(self, checks: list[str]) -> list[str]:
        commands = ["python -m unittest backend.test_hermes_cognitive_os"]
        if "schema_integrity" in checks:
            commands.append("python -m unittest discover backend")
        if "type_check" in checks:
            commands.append("npm run type-check")
        if "frontend_smoke" in checks:
            commands.append("npm run build")
        return list(dict.fromkeys(commands))

    def _confidence(self, checks: list[str]) -> float:
        return round(min(0.92, 0.68 + len(checks) * 0.035), 3)

    def _performance_score(self, status: str, regressions: list[str], output_summary: str) -> float:
        base = {"passed": 0.92, "partial": 0.62, "failed": 0.25}[status]
        penalty = min(0.4, len(regressions) * 0.08)
        if "slow" in output_summary.lower() or "timeout" in output_summary.lower():
            penalty += 0.08
        return max(0.0, base - penalty)

    def _get_report(self, report_id: str) -> dict[str, Any]:
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute("SELECT * FROM autonomous_test_reports WHERE id = ?", (report_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown autonomous test report: {report_id}")
        return self._decode(row)

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["test_plan"] = loads(data.get("test_plan"), {})
        data["regressions"] = loads(data.get("regressions"), [])
        return data

