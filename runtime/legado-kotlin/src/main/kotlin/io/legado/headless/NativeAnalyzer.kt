package io.legado.headless

import io.legado.app.model.analyzeRule.AnalyzeRule
import io.legado.headless.protocol.RuntimeError
import com.google.gson.JsonObject

class NativeAnalyzer {
    fun execute(request: JsonObject): Pair<Any?, String?> {
        val operation = request.string("op")
        val rule = request.string("rule")
        val content = request["content"]?.takeUnless { it.isJsonNull }?.let {
            if (it.isJsonPrimitive) it.asString else it.toString()
        } ?: ""
        val analyzer = AnalyzeRule().setContent(content, request.stringOrNull("base_url"))
        request.stringOrNull("redirect_url")?.let(analyzer::setRedirectUrl)

        return when (operation) {
            "extract_string" -> analyzer.getString(rule) to "string"
            "extract_list" -> analyzer.getStringList(rule).orEmpty() to "list"
            "extract_elements" -> analyzer.getElements(rule).map { it.toString() } to "list"
            "resolve_url" -> analyzer.getString(rule, isUrl = true) to "string"
            else -> throw RuntimeFailure(
                RuntimeError("UNSUPPORTED_OPERATION", "Unsupported runtime operation: $operation")
            )
        }
    }
}

internal class RuntimeFailure(val runtimeError: RuntimeError) : RuntimeException(runtimeError.message)

internal fun JsonObject.string(name: String): String =
    get(name)?.takeUnless { it.isJsonNull }?.asString.orEmpty()

internal fun JsonObject.stringOrNull(name: String): String? =
    get(name)?.takeUnless { it.isJsonNull }?.asString?.takeIf(String::isNotEmpty)
