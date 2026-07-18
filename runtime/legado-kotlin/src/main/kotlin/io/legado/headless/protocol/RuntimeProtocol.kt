package io.legado.headless.protocol

data class RuntimeTrace(
    val engine: String = "legado-kotlin",
    val engineCommit: String = "2c340d48bb1b9537690ec31eb9c23a57307f30a3",
    val steps: List<Map<String, Any?>> = emptyList(),
    val elapsedMs: Long = 0,
    val cacheReads: List<String> = emptyList(),
    val cacheWrites: List<String> = emptyList(),
)

data class RuntimeError(
    val code: String,
    val message: String,
    val details: Map<String, Any?> = emptyMap(),
)

data class RuntimeResponse(
    val id: String,
    val protocolVersion: Int = 1,
    val success: Boolean,
    val value: Any? = null,
    val valueType: String? = null,
    val trace: RuntimeTrace = RuntimeTrace(),
    val error: RuntimeError? = null,
)
