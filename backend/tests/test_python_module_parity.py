import pytest

from app.infrastructure.legado.engine.runtime_facade import (
    LegadoRuntimeFacade,
    migration_gate_passed,
)


def test_python_migration_gate_requires_zero_diffs_and_stable_runs():
    assert migration_gate_passed(unexplained_diffs=0, golden_cases=100, real_source_runs=20, fallback_rate=0.0)
    assert not migration_gate_passed(unexplained_diffs=1, golden_cases=100, real_source_runs=20, fallback_rate=0.0)
    assert not migration_gate_passed(unexplained_diffs=0, golden_cases=99, real_source_runs=20, fallback_rate=0.0)
    assert not migration_gate_passed(unexplained_diffs=0, golden_cases=100, real_source_runs=20, fallback_rate=0.01)


def test_facade_rejects_unverified_python_primary_module():
    facade = LegadoRuntimeFacade(native_client=object(), fallback=object(), mode="python_primary")
    with pytest.raises(ValueError, match="migration gate"):
        facade.set_module_mode("rule_parser", "python_primary", {
            "unexplained_diffs": 1,
            "golden_cases": 100,
            "real_source_runs": 20,
            "fallback_rate": 0.0,
        })
