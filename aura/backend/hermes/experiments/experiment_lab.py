from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class AIExperimentLab:
    """Runs deterministic prompt/workflow/agent comparisons and stores the winner."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def run_experiment(
        self,
        name: str,
        task: str,
        variants: list[dict[str, Any]],
        metric_weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        clean_name = name.strip() or "Akansha Experiment"
        if len(variants) < 2:
            raise ValueError("At least two variants are required for an experiment")
        weights = metric_weights or {"accuracy": 0.4, "latency": 0.2, "safety": 0.2, "cost": 0.1, "stability": 0.1}
        experiment_id = f"experiment_{uuid4().hex}"
        now = utc_now()
        runs = [self._score_variant(experiment_id, task, variant, weights) for variant in variants]
        winner = max(runs, key=lambda item: item["score"])
        confidence = self._winner_confidence(runs)
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT INTO experiments(id, name, task, variants, status, winner, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, ?)
                """,
                (experiment_id, clean_name, task, dumps(variants), dumps(winner), confidence, now, now),
            )
            for run in runs:
                conn.execute(
                    """
                    INSERT INTO experiment_runs(
                        id, experiment_id, variant_name, variant_type, score, metrics,
                        result, confidence, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run["id"],
                        experiment_id,
                        run["variant_name"],
                        run["variant_type"],
                        run["score"],
                        dumps(run["metrics"]),
                        dumps(run["result"]),
                        run["confidence"],
                        now,
                    ),
                )
        return {
            "id": experiment_id,
            "name": clean_name,
            "task": task,
            "runs": runs,
            "winner": winner,
            "confidence": confidence,
            "status": "completed",
        }

    def list_experiments(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [self._decode_experiment(row) for row in rows]

    def _score_variant(
        self,
        experiment_id: str,
        task: str,
        variant: dict[str, Any],
        weights: dict[str, float],
    ) -> dict[str, Any]:
        name = str(variant.get("name") or variant.get("id") or f"variant_{uuid4().hex[:6]}")
        variant_type = str(variant.get("type") or "workflow")
        body = dumps(variant)
        fingerprint = stable_fingerprint(f"{task}:{name}:{body}")
        completeness = min(1.0, len(body) / 600)
        validation_signal = 1.0 if any(word in body.lower() for word in ["validate", "test", "source", "rollback"]) else 0.55
        safety_signal = 1.0 if "approval" in body.lower() or "risk" in body.lower() else 0.68
        latency_signal = 1.0 - min(0.45, len(body) / 4000)
        cost_signal = 1.0 - min(0.4, len(variant.get("agents", [])) * 0.05 if isinstance(variant.get("agents"), list) else 0.08)
        stability_signal = 0.75 + (0.1 if fingerprint else 0.0)
        metrics = {
            "accuracy": round((completeness * 0.45) + (validation_signal * 0.55), 3),
            "latency": round(latency_signal, 3),
            "safety": round(safety_signal, 3),
            "cost": round(cost_signal, 3),
            "stability": round(min(1.0, stability_signal), 3),
        }
        score = sum(metrics[key] * weights.get(key, 0.0) for key in metrics)
        return {
            "id": f"run_{uuid4().hex}",
            "experiment_id": experiment_id,
            "variant_name": name,
            "variant_type": variant_type,
            "score": round(score, 4),
            "metrics": metrics,
            "result": {"selected_for": task, "fingerprint": fingerprint},
            "confidence": round(min(0.95, max(0.55, score)), 3),
        }

    def _winner_confidence(self, runs: list[dict[str, Any]]) -> float:
        ordered = sorted((float(run["score"]) for run in runs), reverse=True)
        if len(ordered) < 2:
            return round(ordered[0], 3) if ordered else 0.0
        margin = ordered[0] - ordered[1]
        return round(min(0.95, max(0.55, ordered[0] + margin * 0.5)), 3)

    def _decode_experiment(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["variants"] = loads(data.get("variants"), [])
        data["winner"] = loads(data.get("winner"), {})
        return data

