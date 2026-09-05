from copy import deepcopy

from app.infrastructure.legado.engine.models import RepairResult


def repair_source_rules(source: dict) -> RepairResult:
    updated = deepcopy(source)
    diagnostics = []
    changed = False
    if "enabled" not in updated:
        updated["enabled"] = True
        diagnostics.append("added default enabled flag")
        changed = True
    for field in ("ruleToc", "ruleContent"):
        if not updated.get(field):
            updated[field] = "@css:body"
            diagnostics.append(f"filled fallback for {field}")
            changed = True
    return RepairResult(changed=changed, updated=updated, diagnostics=diagnostics)
