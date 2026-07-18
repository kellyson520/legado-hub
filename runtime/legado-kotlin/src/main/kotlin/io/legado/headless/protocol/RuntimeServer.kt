package io.legado.headless.protocol

import com.google.gson.Gson
import com.google.gson.JsonParseException
import com.google.gson.JsonParser
import io.legado.headless.NativeAnalyzer
import io.legado.headless.RuntimeFailure
import io.legado.headless.string
import io.legado.headless.ports.CacheTraceEvent
import io.legado.headless.ports.HttpTraceEvent
import io.legado.headless.ports.RuntimeTraceContext
import java.net.URL

class RuntimeServer(
    private val analyzer: NativeAnalyzer = NativeAnalyzer(),
    private val gson: Gson = Gson(),
) {
    fun dispatchLine(line: String): String {
        val started = System.nanoTime()
        val previousTrace = RuntimeTraceContext.begin()
        var id = ""
        var request: com.google.gson.JsonObject? = null
        return try {
            val parsedRequest = JsonParser.parseString(line).asJsonObject
            request = parsedRequest
            id = parsedRequest.string("id")
            val protocolVersion = parsedRequest["protocol_version"]?.asInt ?: 1
            if (protocolVersion != 1) {
                return response(
                    RuntimeResponse(
                        id = id,
                        protocolVersion = 1,
                        success = false,
                        trace = trace(started, parsedRequest),
                        error = RuntimeError("PROTOCOL_VERSION_UNSUPPORTED", "protocol_version must be 1"),
                    )
                )
            }
            when (parsedRequest.string("op")) {
                "ping" -> response(
                    RuntimeResponse(id = id, success = true, value = "pong", valueType = "string", trace = trace(started, parsedRequest))
                )
                "capabilities" -> response(
                    RuntimeResponse(
                        id = id,
                        success = true,
                        value = mapOf(
                            "engine" to "legado-kotlin",
                            "engine_commit" to "2c340d48bb1b9537690ec31eb9c23a57307f30a3",
                            "operations" to listOf("ping", "capabilities", "extract_string", "extract_list", "extract_elements", "resolve_url"),
                            "bridges" to listOf("http", "cache"),
                            "trace_fields" to listOf(
                                "stage",
                                "operation",
                                "rule_length",
                                "content_length",
                                "content_type",
                                "cache_events",
                                "http_events",
                            ),
                        ),
                        valueType = "object",
                        trace = trace(started, parsedRequest),
                    )
                )
                else -> {
                    val (value, valueType) = analyzer.execute(parsedRequest)
                    response(
                        RuntimeResponse(
                            id = id,
                            success = true,
                            value = value,
                            valueType = valueType,
                            trace = trace(started, parsedRequest),
                            context = parsedRequest["context"]?.takeUnless { it.isJsonNull },
                        )
                    )
                }
            }
        } catch (error: RuntimeFailure) {
            response(
                RuntimeResponse(id = id, success = false, trace = trace(started, request), error = error.runtimeError)
            )
        } catch (error: JsonParseException) {
            response(
                RuntimeResponse(
                    id = id,
                    success = false,
                    trace = trace(started, request),
                    error = RuntimeError("MALFORMED_REQUEST", "Request is not valid JSON"),
                )
            )
        } catch (error: Exception) {
            response(
                RuntimeResponse(
                    id = id,
                    success = false,
                    trace = trace(started, request),
                    error = RuntimeError("RUNTIME_ERROR", error.message ?: error::class.simpleName.orEmpty()),
                )
            )
        } finally {
            RuntimeTraceContext.restore(previousTrace)
        }
    }

    private fun response(value: RuntimeResponse): String = gson.toJson(value)

    private fun trace(started: Long, request: com.google.gson.JsonObject? = null): RuntimeTrace {
        val cacheEvents = RuntimeTraceContext.snapshotCache().map(::safeCacheEvent)
        val httpEvents = RuntimeTraceContext.snapshotHttp().map(::safeHttpEvent)
        return RuntimeTrace(
            elapsedMs = (System.nanoTime() - started) / 1_000_000,
            stage = request?.get("stage")?.takeUnless { it.isJsonNull }?.asString,
            operation = request?.get("op")?.takeUnless { it.isJsonNull }?.asString,
            ruleLength = request?.get("rule")?.takeUnless { it.isJsonNull }?.asString?.length ?: 0,
            contentLength = request?.get("content")?.takeUnless { it.isJsonNull }?.let { content ->
                if (content.isJsonPrimitive && content.asJsonPrimitive.isString) content.asString.length else content.toString().length
            } ?: 0,
            contentType = request?.get("content_type")?.takeUnless { it.isJsonNull }?.asString,
            cacheReads = cacheEvents.filter { it.operation == "get" }.map(::compactCacheEvent),
            cacheWrites = cacheEvents.filter { it.operation != "get" }.map(::compactCacheEvent),
            cacheEvents = cacheEvents,
            httpEvents = httpEvents,
        )
    }

    private fun safeCacheEvent(event: CacheTraceEvent): CacheTraceEvent = event.copy(scope = safeScope(event.scope))

    private fun safeScope(scope: String): String {
        if (scope.isBlank()) return "default"
        return runCatching { URL(scope).host.takeIf(String::isNotBlank) ?: scope.take(96) }
            .getOrDefault(scope.take(96))
    }

    private fun safeHttpEvent(event: HttpTraceEvent): HttpTraceEvent = event.copy(host = event.host.take(255))

    private fun compactCacheEvent(event: CacheTraceEvent): String = buildString {
        append(event.scope.ifBlank { "default" })
        append("#")
        append(event.keyLength)
        append(":")
        append(event.operation)
        event.found?.let { append(if (it) ":hit" else ":miss") }
        event.changed?.let { append(if (it) ":changed" else ":unchanged") }
        event.errorCode?.let { append(":error=").append(it) }
    }
}
