from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, utc_now
from .common import clamp


class VerificationRecheckEngine:
    """Safety and factual recheck gate before real-world actions.

    The engine never approves irreversible work by itself. It calculates checks,
    records an audit row, and returns whether execution is allowed after user
    approval and source verification.
    """

    IRREVERSIBLE_ACTIONS = {"purchase", "booking", "payment", "account_change", "share_private_information"}

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def verify(
        self,
        action_type: str,
        action_id: str,
        payload: dict[str, Any],
        approved: bool = False,
        irreversible: bool | None = None,
    ) -> dict[str, Any]:
        actual_irreversible = action_type in self.IRREVERSIBLE_ACTIONS if irreversible is None else irreversible
        checks = [
            self._price_check(payload),
            self._availability_check(payload),
            self._duplicate_check(payload),
            self._schedule_conflict_check(payload),
            self._payment_check(action_type, approved, actual_irreversible),
            self._expired_link_check(payload),
            self._assumption_check(payload),
        ]
        conflicts = [check for check in checks if check["severity"] in {"blocker", "warning"}]
        confidence = self._confidence(checks)
        allowed = approved and not any(check["severity"] == "blocker" for check in checks)
        if actual_irreversible and not approved:
            allowed = False
        audit = {
            "id": f"verification_{uuid4().hex}",
            "action_type": action_type,
            "action_id": action_id,
            "checks": checks,
            "conflicts": conflicts,
            "confidence": confidence,
            "approved": approved,
            "irreversible": actual_irreversible,
            "requires_approval": actual_irreversible and not approved,
            "allowed_to_execute": allowed,
            "created_at": utc_now(),
        }
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT INTO verification_audits(
                    id, action_type, action_id, checks, conflicts, confidence,
                    approved, irreversible, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit["id"],
                    action_type,
                    action_id,
                    dumps(checks),
                    dumps(conflicts),
                    confidence,
                    int(approved),
                    int(actual_irreversible),
                    audit["created_at"],
                ),
            )
        return audit

    def audits(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM verification_audits ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        from ..database.store import loads

        decoded = []
        for row in rows:
            data = dict(row)
            data["checks"] = loads(data.get("checks"), [])
            data["conflicts"] = loads(data.get("conflicts"), [])
            data["approved"] = bool(data.get("approved"))
            data["irreversible"] = bool(data.get("irreversible"))
            decoded.append(data)
        return decoded

    def _price_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidates = payload.get("candidates") or payload.get("options") or []
        changed = [item.get("name") or item.get("title") for item in candidates if item.get("price_changed")]
        return {
            "name": "price_recheck",
            "passed": not changed,
            "severity": "warning" if changed else "info",
            "message": "Prices changed since comparison" if changed else "No price-change flags detected",
            "evidence": changed,
        }

    def _availability_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidates = payload.get("candidates") or payload.get("options") or []
        unavailable = [
            item.get("name") or item.get("title")
            for item in candidates
            if item.get("availability") is False or item.get("available") is False
        ]
        no_candidates = bool(payload.get("missing_required"))
        return {
            "name": "availability_recheck",
            "passed": not unavailable and not no_candidates,
            "severity": "blocker" if no_candidates else "warning" if unavailable else "info",
            "message": "Source candidates are required before execution" if no_candidates else "Unavailable options detected" if unavailable else "Availability check passed",
            "evidence": unavailable,
        }

    def _duplicate_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        duplicate = bool(payload.get("duplicate_risk"))
        return {
            "name": "duplicate_action_check",
            "passed": not duplicate,
            "severity": "warning" if duplicate else "info",
            "message": "Possible duplicate action detected" if duplicate else "No duplicate action signal detected",
            "evidence": payload.get("duplicate_risk_reason", ""),
        }

    def _schedule_conflict_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        conflicts = payload.get("schedule_conflicts") or []
        return {
            "name": "schedule_conflict_check",
            "passed": not conflicts,
            "severity": "blocker" if conflicts else "info",
            "message": "Schedule conflicts must be resolved" if conflicts else "No schedule conflicts detected",
            "evidence": conflicts,
        }

    def _payment_check(self, action_type: str, approved: bool, irreversible: bool) -> dict[str, Any]:
        blocked = irreversible and not approved
        return {
            "name": "payment_and_irreversible_action_gate",
            "passed": not blocked,
            "severity": "blocker" if blocked else "info",
            "message": "Explicit owner approval required before irreversible execution" if blocked else "Approval gate satisfied or action is reversible",
            "evidence": {"action_type": action_type, "approved": approved, "irreversible": irreversible},
        }

    def _expired_link_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        links = payload.get("links") or []
        expired = [link for link in links if isinstance(link, dict) and link.get("expired")]
        return {
            "name": "expired_link_check",
            "passed": not expired,
            "severity": "warning" if expired else "info",
            "message": "Expired links detected" if expired else "No expired-link signal detected",
            "evidence": expired,
        }

    def _assumption_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        assumptions = payload.get("unverified_assumptions") or []
        return {
            "name": "assumption_recheck",
            "passed": not assumptions,
            "severity": "warning" if assumptions else "info",
            "message": "Unverified assumptions should be confirmed" if assumptions else "No unverified assumptions reported",
            "evidence": assumptions,
        }

    def _confidence(self, checks: list[dict[str, Any]]) -> float:
        if not checks:
            return 0.5
        penalties = {"info": 0.0, "warning": 0.08, "blocker": 0.22}
        score = 0.92 - sum(penalties.get(check["severity"], 0.1) for check in checks)
        return round(clamp(score, 0.15, 0.96), 3)
