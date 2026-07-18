package io.legado.headless.ports

data class HttpRequestSpec(
    val method: String,
    val url: String,
    val headers: Map<String, String> = emptyMap(),
    val body: String? = null,
    val timeoutMs: Long = 15_000,
    val cookieScope: String? = null,
)

data class HttpResponse(
    val status: Int,
    val headers: Map<String, String> = emptyMap(),
    val body: String = "",
    val finalUrl: String? = null,
    val charset: String? = null,
    val elapsedMs: Long = 0,
    val errorCode: String? = null,
)

fun interface HttpBridge {
    fun request(spec: HttpRequestSpec): HttpResponse
}
