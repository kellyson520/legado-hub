package io.legado.headless.protocol

import com.google.gson.Gson
import com.google.gson.JsonParseException
import com.google.gson.JsonParser
import io.legado.headless.NativeAnalyzer
import io.legado.headless.RuntimeFailure
import io.legado.headless.string

class RuntimeServer(
    private val analyzer: NativeAnalyzer = NativeAnalyzer(),
    private val gson: Gson = Gson(),
) {
    fun dispatchLine(line: String): String {
        val started = System.nanoTime()
        var id = ""
        return try {
            val request = JsonParser.parseString(line).asJsonObject
            id = request.string("id")
            val protocolVersion = request["protocol_version"]?.asInt ?: 1
            if (protocolVersion != 1) {
                return response(
                    RuntimeResponse(
                        id = id,
                        protocolVersion = 1,
                        success = false,
                        trace = trace(started),
                        error = RuntimeError("PROTOCOL_VERSION_UNSUPPORTED", "protocol_version must be 1"),
                    )
                )
            }
            when (request.string("op")) {
                "ping" -> response(
                    RuntimeResponse(id = id, success = true, value = "pong", valueType = "string", trace = trace(started))
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
                        ),
                        valueType = "object",
                        trace = trace(started),
                    )
                )
                else -> {
                    val (value, valueType) = analyzer.execute(request)
                    response(
                        RuntimeResponse(
                            id = id,
                            success = true,
                            value = value,
                            valueType = valueType,
                            trace = trace(started),
                            context = request["context"]?.takeUnless { it.isJsonNull },
                        )
                    )
                }
            }
        } catch (error: RuntimeFailure) {
            response(
                RuntimeResponse(id = id, success = false, trace = trace(started), error = error.runtimeError)
            )
        } catch (error: JsonParseException) {
            response(
                RuntimeResponse(
                    id = id,
                    success = false,
                    trace = trace(started),
                    error = RuntimeError("MALFORMED_REQUEST", "Request is not valid JSON"),
                )
            )
        } catch (error: Exception) {
            response(
                RuntimeResponse(
                    id = id,
                    success = false,
                    trace = trace(started),
                    error = RuntimeError("RUNTIME_ERROR", error.message ?: error::class.simpleName.orEmpty()),
                )
            )
        }
    }

    private fun response(value: RuntimeResponse): String = gson.toJson(value)

    private fun trace(started: Long): RuntimeTrace = RuntimeTrace(
        elapsedMs = (System.nanoTime() - started) / 1_000_000,
    )
}
