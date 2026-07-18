package io.legado.app.help.http

import com.google.gson.Gson
import com.script.buildScriptBindings
import com.script.rhino.RhinoScriptEngine
import org.jsoup.Jsoup
import org.jsoup.nodes.Element
import org.mozilla.javascript.Undefined

data class StrResponse(
    val url: String = "",
    val body: String? = null,
    val code: Int = 200,
    val headers: Map<String, String> = emptyMap(),
    val finalUrl: String? = null,
) {
    /** Rhino-friendly aliases used by existing Legado JavaScript sources. */
    fun body(): String = body.orEmpty()
    fun text(): String = body.orEmpty()
    fun statusCode(): Int = code
    fun headers(): Map<String, String> = headers
    fun url(): String = finalUrl ?: url
}

object CookieStore {
    private val cookies = linkedMapOf<String, String>()

    @Synchronized
    fun getCookie(tag: String): String = cookies[tag].orEmpty()

    @Synchronized
    fun replaceCookie(tag: String, value: String) {
        if (value.isBlank()) cookies.remove(tag) else cookies[tag] = value
    }

    @Synchronized
    fun removeCookie(tag: String) {
        cookies.remove(tag)
    }

    fun getKey(tag: String, key: String): String {
        return getCookie(tag).split(';')
            .asSequence()
            .map(String::trim)
            .mapNotNull { part ->
                val index = part.indexOf('=')
                if (index <= 0 || part.substring(0, index).trim() != key) null
                else part.substring(index + 1).trim()
            }
            .firstOrNull()
            .orEmpty()
    }
}

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
    suspend fun getStrResponse(): StrResponse {
        if (javaScript.isBlank()) return StrResponse(url = url.orEmpty(), body = result)
        val document = HeadlessDocument(Jsoup.parse(html, url.orEmpty()))
        val bindings = buildScriptBindings { binding ->
            binding["document"] = document
            binding["window"] = document
            binding["src"] = html
            binding["result"] = decodeResult(result)
        }
        val scope = RhinoScriptEngine.getRuntimeScope(bindings)
        val code = if (Regex("\\breturn\\b").containsMatchIn(javaScript)) javaScript else "return ($javaScript)"
        val evaluated = runCatching { RhinoScriptEngine.eval(code, scope) }.getOrNull()
        val output = when {
            evaluated == null || evaluated is Undefined -> result
            evaluated is String -> evaluated
            else -> Gson().toJson(evaluated)
        }
        return StrResponse(url = url.orEmpty(), body = output)
    }

    private fun decodeResult(value: String): Any? = runCatching {
        Gson().fromJson(value, Any::class.java)
    }.getOrElse { value }
}

/** Small DOM surface matching the selectors used by Legado WebJS rules. */
class HeadlessDocument(private val document: org.jsoup.nodes.Document) {
    fun querySelector(selector: String): HeadlessElement? = document.select(selector).firstOrNull()?.let(::HeadlessElement)
    fun querySelectorAll(selector: String): Array<HeadlessElement> = document.select(selector).map(::HeadlessElement).toTypedArray()
    fun getElementById(id: String): HeadlessElement? = document.getElementById(id)?.let(::HeadlessElement)
    fun getBody(): HeadlessElement? = document.body()?.let(::HeadlessElement)
    fun getHead(): HeadlessElement? = document.head()?.let(::HeadlessElement)
    fun getTitle(): String = document.title()
    fun getDocumentElement(): HeadlessElement = HeadlessElement(document)
}

class HeadlessElement(private val element: Element) {
    fun getTextContent(): String = element.text()
    fun getInnerText(): String = element.text()
    fun getInnerHTML(): String = element.html()
    fun getOuterHTML(): String = element.outerHtml()
    fun getClassName(): String = element.className()
    fun getId(): String = element.id()
    fun getHref(): String = element.absUrl("href").ifBlank { element.attr("href") }
    fun getAttribute(name: String): String = element.attr(name)
    fun attr(name: String): String = element.attr(name)
    fun querySelector(selector: String): HeadlessElement? = element.select(selector).firstOrNull()?.let(::HeadlessElement)
    fun querySelectorAll(selector: String): Array<HeadlessElement> = element.select(selector).map(::HeadlessElement).toTypedArray()
    fun getChildren(): Array<HeadlessElement> = element.children().map(::HeadlessElement).toTypedArray()
}
