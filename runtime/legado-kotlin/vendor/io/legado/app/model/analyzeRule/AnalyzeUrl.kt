package io.legado.app.model.analyzeRule

import com.google.gson.Gson
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.script.buildScriptBindings
import com.script.rhino.RhinoScriptEngine
import org.mozilla.javascript.Context
import org.mozilla.javascript.Scriptable
import org.mozilla.javascript.ScriptableObject
import io.legado.app.data.entities.BaseSource
import io.legado.app.data.entities.Book
import io.legado.app.data.entities.BookChapter
import io.legado.app.help.JsExtensions
import io.legado.app.help.http.BackstageWebView
import io.legado.app.help.http.CookieStore
import io.legado.app.help.http.StrResponse
import io.legado.headless.ports.HeadlessRuntimeBridges
import io.legado.headless.ports.HttpRequestSpec
import io.legado.headless.ports.HttpResponse
import io.legado.app.utils.NetworkUtils
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.Charset
import java.util.Locale
import java.util.regex.Pattern
import kotlin.coroutines.CoroutineContext
import kotlin.coroutines.EmptyCoroutineContext
import kotlinx.coroutines.runBlocking

/**
 * Headless equivalent of Legado's AnalyzeUrl.
 *
 * It deliberately keeps transport in [HeadlessRuntimeBridges]: the JVM
 * parser owns URL option semantics, while Python owns sockets, cookies,
 * redirects and response decoding. This keeps JS rules deterministic and
 * makes the same request path available to `ajax`, `get`, `post` and `head`.
 */
@Suppress("unused", "MemberVisibilityCanBePrivate")
class AnalyzeUrl(
    private val mUrl: String,
    private val key: String? = null,
    private val page: Int? = null,
    private val speakText: String? = null,
    private val speakSpeed: Int? = null,
    private var baseUrl: String = "",
    private val source: BaseSource? = null,
    private val ruleData: RuleDataInterface? = null,
    private val chapter: BookChapter? = null,
    private val readTimeout: Long? = null,
    private val callTimeout: Long? = null,
    private val coroutineContext: CoroutineContext = EmptyCoroutineContext,
    headerMapF: Map<String, String>? = null,
    private val hasLoginHeader: Boolean = true,
    private val infoMap: MutableMap<String, String>? = null,
) : JsExtensions {
    constructor(mUrl: String) : this(mUrl, null)

    var ruleUrl: String = ""
        private set
    var url: String = ""
        private set
    var type: String? = null
        private set
    val headerMap: LinkedHashMap<String, String> = linkedMapOf()
    var urlNoQuery: String = ""
        private set
    private var body: String? = null
    private var encodedForm: String? = null
    private var charset: String? = null
    private var method: String = "GET"
    private var retry: Int = 0
    private var bodyJs: String? = null
    private var webJs: String? = null
    private var webView: Boolean = false
    private var webViewDelayTime: Long = 0
    private var dnsIp: String? = null
    private var serverID: Long? = null
    private var followRedirects: Boolean = true

    init {
        if (baseUrl.isBlank()) baseUrl = source?.getKey().orEmpty()
        val rawBase = baseUrl
        val baseMatcher = paramPattern.matcher(rawBase)
        if (baseMatcher.find()) baseUrl = rawBase.substring(0, baseMatcher.start())
        headerMapF?.let(headerMap::putAll)
            ?: source?.getHeaderMap(hasLoginHeader)?.let(headerMap::putAll)
        initUrl()
    }

    fun initUrl() {
        ruleUrl = mUrl
        analyzeJs()
        replaceKeyPageJs()
        analyzeUrl()
    }

    private fun analyzeJs() {
        var start = 0
        var result = ruleUrl
        val matcher = jsPattern.matcher(ruleUrl)
        while (matcher.find()) {
            if (matcher.start() > start) {
                val literal = ruleUrl.substring(start, matcher.start()).trim()
                if (literal.isNotEmpty()) result = literal.replace("@result", result)
            }
            val code = matcher.group(2) ?: matcher.group(1).orEmpty()
            result = evalJS(code, result)?.toString().orEmpty()
            start = matcher.end()
        }
        if (ruleUrl.length > start) {
            val literal = ruleUrl.substring(start).trim()
            if (literal.isNotEmpty()) result = literal.replace("@result", result)
        }
        ruleUrl = result
    }

    private fun replaceKeyPageJs() {
        if (ruleUrl.contains("{{") && ruleUrl.contains("}}")) {
            val analyzer = RuleAnalyzer(ruleUrl)
            analyzer.reSetPos()
            val expanded = analyzer.innerRule("{{", "}}") { evalJS(it)?.toString().orEmpty() }
            if (expanded.isNotEmpty()) ruleUrl = expanded
        }
        page?.let { currentPage ->
            val matcher = pagePattern.matcher(ruleUrl)
            val replaced = buildString {
                var cursor = 0
                while (matcher.find()) {
                    append(ruleUrl, cursor, matcher.start())
                    val values = matcher.group(1).orEmpty().split(',')
                    val index = (currentPage - 1).coerceAtLeast(0).coerceAtMost(values.lastIndex)
                    append(values.getOrNull(index)?.trim().orEmpty())
                    cursor = matcher.end()
                }
                append(ruleUrl, cursor, ruleUrl.length)
            }
            ruleUrl = replaced
        }
    }

    private fun analyzeUrl() {
        val matcher = paramPattern.matcher(ruleUrl)
        val urlPart = if (matcher.find()) ruleUrl.substring(0, matcher.start()) else ruleUrl
        url = NetworkUtils.getAbsoluteURL(parseBaseUrl(baseUrl), urlPart)
        if (matcher.find(0)) {
            val optionText = ruleUrl.substring(matcher.end()).trim()
            parseOptions(optionText)
        }
        urlNoQuery = url.substringBefore('?')
        if (method == "GET" && !charset.isNullOrBlank()) {
            url = encodeQuery(url, charset!!)
            urlNoQuery = url.substringBefore('?')
        }
        if (method == "POST" && body != null && !isStructuredBody(body!!)) {
            encodedForm = encodeForm(body!!, charset)
        }
    }

    private fun parseOptions(optionText: String) {
        val options = runCatching { Gson().fromJson(optionText, JsonObject::class.java) }.getOrNull() ?: return
        options.string("method")?.uppercase(Locale.ROOT)?.let { requested ->
            method = when (requested) {
                "POST", "HEAD", "GET" -> requested
                else -> "GET"
            }
        }
        options["headers"]?.let { headerElement ->
            decodeMap(headerElement).forEach { (key, value) -> headerMap[key] = value }
        }
        options["body"]?.let { body = jsonValue(it) }
        type = options.string("type")
        charset = options.string("charset")
        retry = options.int("retry")?.coerceIn(0, 5) ?: 0
        webView = options.boolean("webView")
        webJs = options.string("webJs")
        bodyJs = options.string("bodyJs")
        dnsIp = options.string("dnsIp")
        serverID = options.long("serverID")
        webViewDelayTime = options.long("webViewDelayTime")?.coerceAtLeast(0) ?: 0
        if (options.has("followRedirects")) followRedirects = options.boolean("followRedirects")
        options.string("js")?.let { js ->
            val rewritten = evalJS(js, url)?.toString().orEmpty()
            if (rewritten.isNotBlank()) url = rewritten
        }
    }

    private fun executeRequest(
        requestHeaders: Map<String, String> = headerMap,
        requestMethod: String = method,
        requestBody: String? = body,
        requestUrl: String = url,
        timeoutMs: Long = callTimeout ?: readTimeout ?: 15_000,
        followRedirects: Boolean = this.followRedirects,
    ): HttpResponse {
        val bridge = HeadlessRuntimeBridges.http
            ?: return HttpResponse(status = 503, body = "", finalUrl = requestUrl, errorCode = "BRIDGE_UNAVAILABLE")
        val mergedHeaders = linkedMapOf<String, String>().apply {
            putAll(requestHeaders)
            val scope = cookieScope(requestUrl)
            CookieStore.getCookie(scope).takeIf(String::isNotBlank)?.let { cookie ->
                val existing = entries.firstOrNull { it.key.equals("Cookie", ignoreCase = true) }?.value
                val merged = mergeCookieHeader(existing, cookie)
                removeExisting("Cookie")
                this["Cookie"] = merged
            }
            if (source?.enabledCookieJar == true) this["X-Legado-Cookie-Jar"] = "1"
        }
        var lastResponse = HttpResponse(status = 599, finalUrl = requestUrl, errorCode = "REQUEST_FAILED")
        repeat(retry + 1) {
            lastResponse = bridge.request(
                HttpRequestSpec(
                    method = requestMethod,
                    url = requestUrl,
                    headers = mergedHeaders,
                    body = requestBody,
                    timeoutMs = timeoutMs,
                    cookieScope = cookieScope(requestUrl),
                    followRedirects = followRedirects,
                )
            )
            saveResponseCookies(requestUrl, lastResponse)
            if (lastResponse.errorCode == null && lastResponse.status in 200..399) return lastResponse
        }
        return lastResponse
    }

    fun getStrResponse(
        jsStr: String? = null,
        sourceRegex: String? = null,
        useWebView: Boolean = true,
    ): StrResponse {
        val response = executeRequest(
            requestBody = if (method == "POST" && encodedForm != null) encodedForm else body,
        )
        var responseBody = response.body
        if (webView && useWebView && !webJs.isNullOrBlank()) {
            responseBody = runBlocking {
                BackstageWebView(
                    url = response.finalUrl ?: url,
                    html = response.body,
                    javaScript = webJs.orEmpty(),
                    headerMap = headerMap,
                    tag = source?.getKey(),
                    cacheFirst = true,
                    timeout = callTimeout ?: 15_000,
                    result = Gson().toJson(response.body),
                    isRule = false,
                ).getStrResponse().body.orEmpty()
            }
        }
        val transform = bodyJs ?: jsStr
        if (!transform.isNullOrBlank() && responseBody.isNotEmpty()) {
            responseBody = runCatching { evalJS(transform, responseBody)?.toString().orEmpty() }.getOrElse { responseBody }
        }
        return StrResponse(
            url = url,
            body = responseBody,
            code = response.status,
            headers = response.headers,
            finalUrl = response.finalUrl,
        )
    }

    fun getResponse(): HttpResponse = executeRequest(
        requestBody = if (method == "POST" && encodedForm != null) encodedForm else body,
    )

    fun getByteArray(): ByteArray = getStrResponse().body.orEmpty().toByteArray(resolveCharset())

    fun getInputStream() = getByteArray().inputStream()

    fun isPost(): Boolean = method == "POST"

    @JvmOverloads
    fun get(urlStr: String, headers: Any? = null, timeout: Int? = null): StrResponse =
        requestFromJs("GET", urlStr, headers, timeout)

    @JvmOverloads
    fun post(urlStr: String, body: Any?, headers: Any? = null, timeout: Int? = null): StrResponse =
        requestFromJs("POST", urlStr, headers, timeout, bodyString(body))

    @JvmOverloads
    fun head(urlStr: String, headers: Any? = null, timeout: Int? = null): StrResponse =
        requestFromJs("HEAD", urlStr, headers, timeout)

    @JvmOverloads
    fun connect(urlStr: String, headers: Any? = null, timeout: Int? = null): StrResponse =
        requestFromJs("GET", urlStr, headers, timeout)

    private fun requestFromJs(
        requestMethod: String,
        rawUrl: String,
        rawHeaders: Any?,
        timeout: Int?,
        requestBody: String? = null,
    ): StrResponse {
        val resolved = NetworkUtils.getAbsoluteURL(parseBaseUrl(baseUrl.ifBlank { url }), rawUrl)
        val directHeaders = linkedMapOf<String, String>().apply {
            putAll(headerMap)
            putAll(decodeMap(rawHeaders))
        }
        val response = executeRequest(
            requestHeaders = directHeaders,
            requestMethod = requestMethod,
            requestBody = requestBody,
            requestUrl = resolved,
            timeoutMs = timeout?.toLong() ?: callTimeout ?: 15_000,
            followRedirects = false,
        )
        return StrResponse(
            url = resolved,
            body = response.body,
            code = response.status,
            headers = response.headers,
            finalUrl = response.finalUrl,
        )
    }

    private fun bodyString(value: Any?): String = when (value) {
        null -> ""
        is String -> value
        is JsonElement -> Gson().toJson(value)
        is Scriptable -> {
            val objectValue = JsonObject()
            value.ids.forEach { id ->
                val key = id.toString()
                val item = ScriptableObject.getProperty(value, key)
                if (item != null && item !is org.mozilla.javascript.Undefined) objectValue.addProperty(key, Context.toString(item))
            }
            Gson().toJson(objectValue)
        }
        else -> Gson().toJson(value)
    }

    override fun getSource(): BaseSource? = source

    override fun getTag(): String? = source?.getTag()

    override fun ajax(url: Any): String? = ajax(url, null)

    override fun ajax(url: Any, callTimeout: Long?): String? {
        val rawUrl = if (url is List<*>) url.firstOrNull()?.toString().orEmpty() else url.toString()
        return AnalyzeUrl(
            rawUrl,
            baseUrl = baseUrl,
            source = source,
            ruleData = ruleData,
            chapter = chapter,
            callTimeout = callTimeout,
            coroutineContext = coroutineContext,
        ).getStrResponse().body
    }

    fun evalJS(jsStr: String, result: Any? = null): Any? {
        val bindings = buildScriptBindings { binding ->
            binding["java"] = this
            binding["baseUrl"] = baseUrl
            binding["cookie"] = CookieStore
            binding["source"] = source
            binding["book"] = ruleData as? Book
            binding["chapter"] = chapter
            binding["result"] = result
            binding["page"] = page
            binding["key"] = key
            binding["speakText"] = speakText
            binding["speakSpeed"] = speakSpeed
            binding["infoMap"] = infoMap
        }
        val scope = RhinoScriptEngine.getRuntimeScope(bindings)
        return RhinoScriptEngine.eval(jsStr, scope, coroutineContext)
    }

    private fun saveResponseCookies(requestUrl: String, response: HttpResponse) {
        val scope = cookieScope(requestUrl)
        val setCookies = response.headers.entries
            .filter { it.key.equals("Set-Cookie", ignoreCase = true) || it.key.equals("Set-Cookie2", ignoreCase = true) }
            .flatMap { it.value.split("\n") }
            .mapNotNull { it.substringBefore(';').trim().takeIf(String::isNotBlank) }
        if (setCookies.isNotEmpty()) {
            val merged = mergeCookieHeader(CookieStore.getCookie(scope), setCookies.joinToString("; "))
            CookieStore.replaceCookie(scope, merged)
        }
    }

    private fun cookieScope(targetUrl: String): String = source?.getKey()?.ifBlank { null }
        ?: runCatching { URL(targetUrl).host }.getOrDefault(targetUrl)

    private fun mergeCookieHeader(left: String?, right: String): String {
        val values = linkedMapOf<String, String>()
        listOf(left.orEmpty(), right).flatMap { it.split(';') }.forEach { part ->
            val index = part.indexOf('=')
            if (index > 0) values[part.substring(0, index).trim()] = part.substring(index + 1).trim()
        }
        return values.entries.joinToString("; ") { "${it.key}=${it.value}" }
    }

    private fun MutableMap<String, String>.removeExisting(name: String) {
        keys.filter { it.equals(name, ignoreCase = true) }.toList().forEach(::remove)
    }

    private fun parseBaseUrl(value: String): URL? = value.takeIf(String::isNotBlank)?.let { runCatching { URL(it) }.getOrNull() }

    private fun resolveCharset(): Charset = charset?.let { runCatching { Charset.forName(it) }.getOrNull() } ?: Charsets.UTF_8

    private fun encodeForm(value: String, charsetName: String?): String {
        val encoding = charsetName?.let { runCatching { Charset.forName(it) }.getOrNull() } ?: Charsets.UTF_8
        return value.split('&').joinToString("&") { pair ->
            val index = pair.indexOf('=')
            if (index < 0) URLEncoder.encode(pair, encoding) else {
                val key = URLEncoder.encode(pair.substring(0, index), encoding)
                val item = URLEncoder.encode(pair.substring(index + 1), encoding)
                "$key=$item"
            }
        }
    }

    private fun encodeQuery(value: String, charsetName: String): String {
        val queryStart = value.indexOf('?')
        if (queryStart < 0) return value
        val encoding = runCatching { Charset.forName(charsetName) }.getOrDefault(Charsets.UTF_8)
        val base = value.substring(0, queryStart)
        val query = value.substring(queryStart + 1).split('&').joinToString("&") { pair ->
            val index = pair.indexOf('=')
            if (index < 0) pair else {
                val key = pair.substring(0, index)
                val item = pair.substring(index + 1)
                if (item.contains('%')) pair else "$key=${URLEncoder.encode(item, encoding)}"
            }
        }
        return "$base?$query"
    }

    private fun isStructuredBody(value: String): Boolean = runCatching {
        val trimmed = value.trim()
        trimmed.startsWith("{") || trimmed.startsWith("[")
    }.getOrDefault(false)

    private fun decodeMap(element: Any?): Map<String, String> {
        if (element == null) return emptyMap()
        if (element is Scriptable) {
            val result = linkedMapOf<String, String>()
            element.ids.forEach { id ->
                val key = id.toString()
                val value = ScriptableObject.getProperty(element, key)
                if (value != null && value !is org.mozilla.javascript.Undefined) {
                    result[key] = Context.toString(value)
                }
            }
            if (result.isNotEmpty()) return result
        }
        val json = when (element) {
            is JsonElement -> element
            else -> runCatching { Gson().toJsonTree(element) }.getOrNull()
        } ?: return emptyMap()
        val objectValue = when {
            json.isJsonObject -> json.asJsonObject
            json.isJsonPrimitive && json.asJsonPrimitive.isString -> runCatching { Gson().fromJson(json.asString, JsonObject::class.java) }.getOrNull()
            else -> null
        } ?: return emptyMap()
        return objectValue.entries.associate { (key, value) -> key to jsonValue(value) }
    }

    private fun jsonValue(value: JsonElement): String = when {
        value.isJsonNull -> ""
        value.isJsonPrimitive -> value.asString
        else -> Gson().toJson(value)
    }

    private fun JsonObject.string(name: String): String? = get(name)?.takeUnless { it.isJsonNull }?.let(::jsonValue)?.takeIf(String::isNotBlank)
    private fun JsonObject.int(name: String): Int? = get(name)?.takeUnless { it.isJsonNull }?.let { runCatching { it.asInt }.getOrNull() }
    private fun JsonObject.long(name: String): Long? = get(name)?.takeUnless { it.isJsonNull }?.let { runCatching { it.asLong }.getOrNull() }
    private fun JsonObject.boolean(name: String): Boolean = get(name)?.takeUnless { it.isJsonNull }?.let { runCatching { it.asBoolean }.getOrDefault(false) } ?: false

    companion object {
        val paramPattern: Pattern = Pattern.compile("\\s*,\\s*(?=\\{)")
        private val pagePattern = Pattern.compile("<(.*?)>")
        private val jsPattern = Pattern.compile("<js>([\\w\\W]*?)</js>|@js:([\\w\\W]*)", Pattern.CASE_INSENSITIVE)
    }
}
