class EngineService:
    def __init__(self, *, evaluator=None, repairer=None, harness=None):
        self._evaluator = evaluator
        self._repairer = repairer
        self._harness = harness

    async def generate(self, payload: dict) -> dict:
        return {
            "job_type": "generate",
            "input_url": payload["url"],
            "sample_present": bool(payload.get("sample")),
        }

    async def evaluate(self, payload: dict) -> dict:
        if self._evaluator is None:
            raise RuntimeError("engine evaluator is not configured")
        return self._evaluator(payload["source"]).__dict__

    async def repair(self, payload: dict) -> dict:
        if self._repairer is None:
            raise RuntimeError("engine repairer is not configured")
        return self._repairer(payload["source"]).__dict__

    async def test_rule(self, payload: dict) -> dict:
        if self._harness is None:
            raise RuntimeError("engine harness is not configured")
        return self._harness(payload["rule"], payload["sample"]).__dict__
