package io.legado.headless.protocol

import com.google.gson.annotations.SerializedName
import io.legado.headless.ports.CacheTraceEvent
import io.legado.headless.ports.HttpTraceEvent

data class RuntimeTrace(
    val engine: String = "legado-kotlin",
    @SerializedName("engine_commit")
    val engineCommit: String = "2c340d48bb1b9537690ec31eb9c23a57307f30a3",
    val steps: List<Map<String, Any?>> = emptyList(),
    @SerializedName("elapsed_ms")
    val elapsedMs: Long = 0,
    val stage: String? = null,
    val operation: String? = null,
    @SerializedName("rule_length")
    val ruleLength: Int = 0,
    @SerializedName("content_length")
    val contentLength: Int = 0,
    @SerializedName("content_type")
    val contentType: String? = null,
    @SerializedName("cache_reads")
    val cacheReads: List<String> = emptyList(),
    @SerializedName("cache_writes")
    val cacheWrites: List<String> = emptyList(),
    @SerializedName("cache_events")
    val cacheEvents: List<CacheTraceEvent> = emptyList(),
    @SerializedName("http_events")
    val httpEvents: List<HttpTraceEvent> = emptyList(),
)

data class RuntimeError(
    val code: String,
    val message: String,
    val details: Map<String, Any?> = emptyMap(),
)

data class RuntimeResponse(
    val id: String,
    @SerializedName("protocol_version")
    val protocolVersion: Int = 1,
    val success: Boolean,
    val value: Any? = null,
    @SerializedName("value_type")
    val valueType: String? = null,
    val trace: RuntimeTrace = RuntimeTrace(),
    val context: Any? = null,
    val error: RuntimeError? = null,
)
