package io.legado.app.model.analyzeRule

import io.legado.app.data.entities.BaseSource
import io.legado.app.help.http.StrResponse
import io.legado.app.model.analyzeRule.RuleDataInterface
import io.legado.headless.ports.HeadlessRuntimeBridges
import io.legado.headless.ports.HttpRequestSpec
import java.util.regex.Pattern
import kotlin.coroutines.CoroutineContext

/**
 * Headless request adapter. The real request is supplied by the Python bridge
 * once the JSON-RPC transport is active; this class preserves the native API.
 */
class AnalyzeUrl(
    private val mUrl: String,
    private val key: String? = null,
    private val page: Int? = null,
    private val source: BaseSource? = null,
    private val ruleData: RuleDataInterface? = null,
    private val callTimeout: Long? = null,
    private val coroutineContext: CoroutineContext = kotlin.coroutines.EmptyCoroutineContext,
) {
    fun getStrResponse(): StrResponse {
        val bridge = HeadlessRuntimeBridges.http
            ?: return StrResponse(body = "", code = 503)
        val response = bridge.request(
            HttpRequestSpec(
                method = "GET",
                url = mUrl,
                headers = source?.getHeaderMap(true).orEmpty(),
                timeoutMs = callTimeout ?: 15_000,
            )
        )
        return StrResponse(body = response.body, code = response.status, headers = response.headers)
    }

    companion object {
        val paramPattern: Pattern = Pattern.compile(",\\s*(\\{[\\w\\W]*})$")
    }
}
