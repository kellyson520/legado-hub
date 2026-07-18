from app.infrastructure.legado.engine.native_models import RuntimeResult
from app.infrastructure.legado.engine.runtime_facade import LegadoRuntimeFacade


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def call(self, operation, payload, timeout):
        self.calls.append((operation, payload, timeout))
        return self.result


class FakeFallback:
    def __init__(self):
        self.calls = []

    def extract(self, content, rule, *, operation, **kwargs):
        self.calls.append((content, rule, operation, kwargs))
        return RuntimeResult(success=True, value=["fallback"])


def test_facade_does_not_fallback_on_semantic_empty_result():
    client = FakeClient(RuntimeResult(success=True, value=[], value_type="list"))
    fallback = FakeFallback()
    facade = LegadoRuntimeFacade(native_client=client, fallback=fallback, mode="native_kotlin")

    result = facade.extract("<div></div>", "#missing@text", operation="extract_list", stage="content")

    assert result.success
    assert result.value == []
    assert fallback.calls == []


def test_facade_falls_back_only_when_native_runtime_is_unavailable():
    client = FakeClient(RuntimeResult(success=False, error_code="RUNTIME_UNAVAILABLE"))
    fallback = FakeFallback()
    facade = LegadoRuntimeFacade(native_client=client, fallback=fallback, mode="native_kotlin")

    result = facade.extract("<div></div>", "#content@text", operation="extract_string", stage="content")

    assert result.success
    assert result.value == ["fallback"]
    assert len(fallback.calls) == 1


def test_shadow_mode_records_structured_diff():
    client = FakeClient(RuntimeResult(success=True, value="native", value_type="string"))
    fallback = FakeFallback()
    facade = LegadoRuntimeFacade(native_client=client, fallback=fallback, mode="python_shadow")

    facade.extract("<div></div>", "div@text", operation="extract_string", stage="content")

    assert len(facade.diffs) == 1
    assert facade.diffs[0]["code"] == "NATIVE_SEMANTICS_MISMATCH"
    assert facade.diffs[0]["stage"] == "content"


def test_facade_merges_native_context_updates_for_following_rules():
    client = FakeClient(RuntimeResult(
        success=True,
        value="updated",
        value_type="string",
        context={"variables": {"token": "updated"}},
    ))
    context = {"source": {"bookSourceUrl": "https://example.test"}, "variables": {"token": "old"}}
    facade = LegadoRuntimeFacade(native_client=client, mode="native_kotlin")

    facade.extract("<div />", "@js:return java.get('token')", context=context)

    assert context["variables"]["token"] == "updated"
    assert client.calls[0][1]["context"]["variables"]["token"] == "old"


def test_python_fallback_trace_keeps_request_shape_without_content():
    client = FakeClient(RuntimeResult(success=False, error_code="RUNTIME_UNAVAILABLE"))
    facade = LegadoRuntimeFacade(native_client=client, mode="native_kotlin")

    result = facade.extract(
        "<div>private body</div>",
        "div@text",
        operation="extract_string",
        stage="content",
    )

    assert result.success
    assert result.trace["stage"] == "content"
    assert result.trace["operation"] == "extract_string"
    assert result.trace["rule_length"] == len("div@text")
    assert result.trace["content_length"] == len("<div>private body</div>")
    assert "private body" not in result.trace
