package io.legado.headless.protocol

import com.google.gson.Gson
import io.legado.headless.ports.HttpBridge
import io.legado.headless.ports.HttpRequestSpec
import io.legado.headless.ports.HttpResponse
import java.io.BufferedReader
import java.io.PrintWriter
import java.util.UUID

class StdioHttpBridge(
    private val input: BufferedReader,
    private val output: PrintWriter,
    private val gson: Gson = Gson(),
) : HttpBridge {
    override fun request(spec: HttpRequestSpec): HttpResponse {
        val id = UUID.randomUUID().toString()
        output.println(
            gson.toJson(
                mapOf(
                    "type" to "bridge_http",
                    "id" to id,
                    "request" to mapOf(
                        "method" to spec.method,
                        "url" to spec.url,
                        "headers" to spec.headers,
                        "body" to spec.body,
                        "timeout_ms" to spec.timeoutMs,
                        "cookie_scope" to spec.cookieScope,
                    ),
                )
            )
        )
        output.flush()

        while (true) {
            val line = input.readLine() ?: throw IllegalStateException("bridge input closed")
            val message = gson.fromJson(line, Map::class.java)
            if (message["type"] != "bridge_http_result" || message["id"] != id) continue
            val response = message["response"] as? Map<*, *> ?: emptyMap<String, Any?>()
            return HttpResponse(
                status = (response["status"] as? Number)?.toInt() ?: 599,
                headers = (response["headers"] as? Map<*, *>)
                    ?.mapNotNull { (key, value) -> key?.toString()?.let { it to value.toString() } }
                    ?.toMap()
                    .orEmpty(),
                body = response["text"]?.toString() ?: response["body"]?.toString().orEmpty(),
                finalUrl = response["final_url"]?.toString(),
                elapsedMs = (response["elapsed_ms"] as? Number)?.toLong() ?: 0,
                errorCode = response["error_code"]?.toString(),
            )
        }
    }
}
