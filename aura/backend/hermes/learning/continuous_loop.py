from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .reflection_engine import ReflectionEngine
from ..database.store import CognitiveStore
from ..evolution.self_evolution import SelfEvolutionEngine
from ..memory.memory_compression import MemoryCompressionEngine
from ..operating_system.cognitive_health import CognitiveHealthEngine
from ..twin import CognitiveDigitalTwinEngine, FutureSimulationEngine


logger = logging.getLogger("akansha.hermes.loop")


@dataclass
class LearningLoopConfig:
    interval_seconds: int = 300
    max_cycles: int = 1


class ContinuousLearningLoop:
    """Bounded maintenance loop; never runs forever inside request handlers."""

    def __init__(self, store: CognitiveStore, config: LearningLoopConfig | None = None) -> None:
        self.store = store
        self.config = config or LearningLoopConfig()
        self.compression = MemoryCompressionEngine(store)
        self.reflection = ReflectionEngine(store)
        self.self_evolution = SelfEvolutionEngine(store)
        self.cognitive_health = CognitiveHealthEngine(store)
        self.digital_twin = CognitiveDigitalTwinEngine(store)
        self.future_simulation = FutureSimulationEngine(store)
        self._running = False

    async def run_once(self) -> dict:
        compression = self.compression.compress()
        evolution = self.self_evolution.optimize("bounded continuous learning maintenance")
        twin_profile = self.digital_twin.rebuild_profile()
        latest_simulations = self.future_simulation.latest(limit=5)
        health = self.cognitive_health.snapshot()
        return {
            "memory_compression": compression,
            "self_evolution": evolution,
            "digital_twin": twin_profile,
            "future_simulations": latest_simulations,
            "cognitive_health": health,
        }

    async def run_bounded(self) -> list[dict]:
        if self._running:
            return [{"skipped": "loop_already_running"}]
        self._running = True
        results: list[dict] = []
        try:
            for _ in range(max(1, min(self.config.max_cycles, 5))):
                results.append(await self.run_once())
                if self.config.max_cycles > 1:
                    await asyncio.sleep(max(1, min(self.config.interval_seconds, 3600)))
        finally:
            self._running = False
        return results
