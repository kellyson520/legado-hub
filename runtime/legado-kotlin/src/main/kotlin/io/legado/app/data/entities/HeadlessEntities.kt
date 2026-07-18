package io.legado.app.data.entities

import com.google.gson.Gson
import io.legado.app.model.analyzeRule.RuleDataInterface
import io.legado.app.help.http.CookieStore

open class BaseSource(
    private val values: MutableMap<String, String> = linkedMapOf(),
) {
    var header: String?
        get() = values["header"]
        set(value) {
            if (value == null) values.remove("header") else values["header"] = value
        }

    var loginUrl: String?
        get() = values["loginUrl"]
        set(value) {
            if (value == null) values.remove("loginUrl") else values["loginUrl"] = value
        }

    var loginUi: String?
        get() = values["loginUi"]
        set(value) {
            if (value == null) values.remove("loginUi") else values["loginUi"] = value
        }

    var jsLib: String?
        get() = values["jsLib"]
        set(value) {
            if (value == null) values.remove("jsLib") else values["jsLib"] = value
        }

    var enabledCookieJar: Boolean = values["enabledCookieJar"]?.toBooleanStrictOrNull() ?: false
        set(value) {
            field = value
            values["enabledCookieJar"] = value.toString()
        }

    open fun get(key: String): String? = values[key]

    open fun put(key: String, value: String): String {
        values[key] = value
        return value
    }

    open fun getTag(): String? = values["tag"]

    open fun getKey(): String? = values["bookSourceUrl"] ?: values["sourceUrl"]

    /**
     * Decode the same JSON header field used by the Android source model.
     * Dynamic `@js:` headers are evaluated by the owning AnalyzeRule; keeping
     * malformed headers out of the transport is safer than sending a partial
     * request map.
     */
    open fun getHeaderMap(includeAuth: Boolean = true): Map<String, String> {
        val result = linkedMapOf<String, String>()
        val raw = header.orEmpty().trim()
        if (raw.isNotEmpty() && !raw.startsWith("@js:", ignoreCase = true) && !raw.startsWith("<js>", ignoreCase = true)) {
            runCatching {
                Gson().fromJson(raw, Map::class.java)
            }.getOrNull()?.let { decoded ->
                decoded.entries.forEach { (key, value) ->
                    if (key != null && value != null) result[key.toString()] = value.toString()
                }
            }
        }
        if (result.keys.none { it.equals("User-Agent", ignoreCase = true) }) {
            result["User-Agent"] = DEFAULT_USER_AGENT
        }
        if (includeAuth) {
            val loginHeader = values["loginHeader"] ?: values["loginHeaders"]
            if (!loginHeader.isNullOrBlank()) {
                runCatching { Gson().fromJson(loginHeader, Map::class.java) }
                    .getOrNull()?.let { decoded ->
                        decoded.entries.forEach { (key, value) ->
                            if (key != null && value != null) result[key.toString()] = value.toString()
                        }
                    }
            }
            getKey()?.let { scope ->
                CookieStore.getCookie(scope).takeIf(String::isNotBlank)?.let { result["Cookie"] = it }
            }
        }
        return result
    }

    fun values(): Map<String, String> = values.toMap()

    companion object {
        const val DEFAULT_USER_AGENT =
            "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"
    }
}

open class BaseBook(
    override val variableMap: HashMap<String, String> = hashMapOf(),
) : RuleDataInterface {
    override fun putBigVariable(key: String, value: String?) = Unit

    override fun getBigVariable(key: String): String? = null
}

class Book(
    var name: String = "",
    var author: String = "",
    variableMap: HashMap<String, String> = hashMapOf(),
) : BaseBook(variableMap) {
    var bookUrl: String = ""
    var tocUrl: String = ""
    var coverUrl: String = ""
}

class BookSource(values: MutableMap<String, String> = linkedMapOf()) : BaseSource(values)

class BookChapter(
    var title: String = "",
    override val variableMap: HashMap<String, String> = hashMapOf(),
) : RuleDataInterface {
    var url: String = ""
    var index: Int = 0

    override fun putBigVariable(key: String, value: String?) = Unit

    override fun getBigVariable(key: String): String? = null
}

class RssArticle(
    override val variableMap: HashMap<String, String> = hashMapOf(),
) : RuleDataInterface {
    override fun putBigVariable(key: String, value: String?) = Unit

    override fun getBigVariable(key: String): String? = null
}
