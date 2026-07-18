package io.legado.app.help.http

data class StrResponse(
    val body: String? = null,
    val code: Int = 200,
    val headers: Map<String, String> = emptyMap(),
)

object CookieStore

class BackstageWebView(
    private val url: String?,
    private val html: String,
    private val javaScript: String,
    private val headerMap: Map<String, String>?,
    private val tag: String?,
    private val cacheFirst: Boolean,
    private val timeout: Long,
    private val result: String,
    private val isRule: Boolean,
) {
    suspend fun getStrResponse(): StrResponse = StrResponse(body = result)
}
