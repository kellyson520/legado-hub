package io.legado.headless.ports

data class HttpRequestSpec(
    val method: String,
    val url: String,
    val headers: Map<String, String> = emptyMap(),
    val body: String? = null,
    val timeoutMs: Long = 15_000,
    val cookieScope: String? = null,
    val followRedirects: Boolean = true,
    val charset: String? = null,
    val contentType: String? = null,
    val proxy: String? = null,
    val dnsIp: String? = null,
    val origin: String? = null,
    val serverId: Long? = null,
    val acceptBytes: Boolean = false,
)

data class HttpResponse(
    val status: Int,
    val headers: Map<String, String> = emptyMap(),
    val body: String = "",
    val finalUrl: String? = null,
    val charset: String? = null,
    val elapsedMs: Long = 0,
    val errorCode: String? = null,
    val bodyBytes: ByteArray? = null,
)

fun interface HttpBridge {
    fun request(spec: HttpRequestSpec): HttpResponse
}

object HeadlessRuntimeBridges {
    @Volatile
    var http: HttpBridge? = null

    @Volatile
    var cache: CacheBridge? = null
}
