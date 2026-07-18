# Source Agent Joint Test Design

## Goal

Allow the `source_build` Agent to run a bounded, evidence-first joint test of a generated book source. The test must exercise the existing source-to-insight acceptance chain rather than relying on model memory:

1. source build
2. source materialization
3. search
4. table of contents
5. chapter content
6. multi-source complement
7. character and narrative insights

The operation is diagnostic and candidate-only. It never publishes, enables, or mutates a source rule directly.

## Architecture

`source.joint_test` is a built-in `AgentToolRegistry` tool in the `operate` category and is authorized only for `source_build` agents. A dedicated executor owns the boundary between tool arguments and `SourceToInsightAcceptanceService`:

```text
AgentRuntime / AI workspace
        |
        v
AgentToolRegistry -- authorization + tenant scope
        |
        v
SourceJointTestToolExecutor -- bounded arguments + result shaping
        |
        v
SourceToInsightAcceptanceService -- deterministic source/read/complement/insight chain
```

The executor receives the acceptance service through the persistence factory. It must not call the Agent registry from inside the acceptance service, which prevents recursive `source.joint_test` calls and keeps the chain deterministic.

## Tool contract

The tool accepts:

- `source_urls`: one to four absolute HTTP(S) URLs
- `book_name`: required work title, maximum 300 characters
- `author_hint`: optional author hint, maximum 200 characters
- `chapter_index`: zero-based chapter index, from 0 through 100000
- `chapter_title`: optional chapter selector, maximum 300 characters
- `use_ai`: whether the configured character calibration service may run

The executor injects the authorized tenant ID into the scenario. It rejects malformed or oversized inputs with a stable error code and caps the returned report to bounded previews already enforced by the acceptance service. It does not accept source IDs, arbitrary callbacks, publication flags, or filesystem/network commands.

The result is a `ToolResult`. Accepted results contain the acceptance report and a compact summary. Rejected results contain only a stable error code. The report includes an `agent_joint_test` object identifying the tool, enabled status, and ordered stages, so UI and audit consumers can distinguish an Agent-triggered run from a direct smoke test.

## Agent integration

The AI workspace advertises the function schema only when `source.joint_test` is granted. The system prompt explicitly requires the Agent to call it before making source usability or literary-analysis claims. The Agent must cite the returned search, TOC, content, complement, and insight evidence; if the report has no usable chapter content it must state that no conclusion can be made.

The source-build repair Agent receives the same bounded handler through its existing source-build registry wiring. Knowledge Agents remain unable to call the operation directly; they continue using the audited read tools (`source.search`, `toc.get`, and `chapter.fetch`) for already-materialized sources.

## Error handling and safety

- Tenant scope is enforced by `AgentToolRegistry` before handler execution.
- No source publication, enablement, or candidate approval is performed.
- Each source failure is isolated and represented in the report; one failed URL does not abort other URLs.
- Missing downstream services produce `skipped` steps, preserving the existing acceptance semantics.
- Handler exceptions are converted to a bounded rejected result rather than leaking stack traces or credentials.

## Verification

Add focused tests for:

- built-in tool presence and source-build-only authorization;
- rejected unimplemented and oversized calls;
- executor delegation, tenant propagation, summary shaping, and exception conversion;
- optional `agent_joint_test` report metadata;
- unchanged deterministic acceptance behavior.

Run the targeted Python test files with the repository test virtualenv, plus `compileall` and `git diff --check`. Kotlin/Gradle builds remain outside this change.
