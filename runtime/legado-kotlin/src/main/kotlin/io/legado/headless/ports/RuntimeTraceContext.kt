package io.legado.headless.ports

import com.google.gson.annotations.SerializedName

/**
 * Safe, request-local diagnostics collected while a native rule is running.
 * Values, cookies and full page contents are intentionally excluded.
 */
data class CacheTraceEvent(
    val operation: String,
    val scope: String,
    @SerializedName("key_length")
    val keyLength: Int,
    val found: Boolean? = null,
    val changed: Boolean? = null,
    @SerializedName("error_code")
    val errorCode: String? = null,
)

data class HttpTraceEvent(
    val method: String,
    val host: String,
    val status: Int,
    @SerializedName("error_code")
    val errorCode: String? = null,
    @SerializedName("elapsed_ms")
    val elapsedMs: Long = 0,
)

data class RuntimeTraceState(
    val cacheEvents: List<CacheTraceEvent> = emptyList(),
    val httpEvents: List<HttpTraceEvent> = emptyList(),
    val active: Boolean = false,
)

object RuntimeTraceContext {
    private val cacheEvents = ThreadLocal.withInitial<MutableList<CacheTraceEvent>?> { null }
    private val httpEvents = ThreadLocal.withInitial<MutableList<HttpTraceEvent>?> { null }

    fun begin(): RuntimeTraceState {
        val previous = RuntimeTraceState(
            cacheEvents = cacheEvents.get()?.toList().orEmpty(),
            httpEvents = httpEvents.get()?.toList().orEmpty(),
            active = cacheEvents.get() != null || httpEvents.get() != null,
        )
        cacheEvents.set(mutableListOf())
        httpEvents.set(mutableListOf())
        return previous
    }

    fun restore(previous: RuntimeTraceState) {
        if (previous.active) {
            cacheEvents.set(previous.cacheEvents.toMutableList())
            httpEvents.set(previous.httpEvents.toMutableList())
        } else {
            cacheEvents.set(null)
            httpEvents.set(null)
        }
    }

    fun record(event: CacheTraceEvent) {
        cacheEvents.get()?.add(event)
    }

    fun record(event: HttpTraceEvent) {
        httpEvents.get()?.add(event)
    }

    fun snapshotCache(): List<CacheTraceEvent> = cacheEvents.get()?.toList().orEmpty()

    fun snapshotHttp(): List<HttpTraceEvent> = httpEvents.get()?.toList().orEmpty()
}
