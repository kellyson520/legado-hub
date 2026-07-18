from app.infrastructure.legado.engine.native_models import RuntimeResult
from app.infrastructure.legado.engine.rule_selector import RuleSelector, RuleType


class RecordingFacade:
    def __init__(self):
        self.calls = []

    def extract(self, content, rule, **kwargs):
        self.calls.append((content, rule, kwargs))
        return RuntimeResult(success=True, value="native", value_type="string")


def test_rule_selector_delegates_when_runtime_facade_is_in_context():
    facade = RecordingFacade()

    result = RuleSelector.extract(
        "<div>old</div>",
        "div@text",
        is_html=True,
        context={"runtime_facade": facade, "stage": "content"},
    )

    assert result.success
    assert result.value == "native"
    assert result.rule_type == RuleType.AUTO
    assert facade.calls[0][2]["operation"] == "extract_string"
