from app.infrastructure.legado.engine.evaluator import evaluate_source_rules
from app.infrastructure.legado.engine.harness import run_rule_harness
from app.infrastructure.legado.engine.repairer import repair_source_rules


class EngineService:
    async def generate(self, payload: dict) -> dict:
        return {
            "job_type": "generate",
            "input_url": payload["url"],
            "sample_present": bool(payload.get("sample")),
        }

    async def evaluate(self, payload: dict) -> dict:
        return evaluate_source_rules(payload["source"]).__dict__

    async def repair(self, payload: dict) -> dict:
        return repair_source_rules(payload["source"]).__dict__

    async def test_rule(self, payload: dict) -> dict:
        return run_rule_harness(payload["rule"], payload["sample"]).__dict__
