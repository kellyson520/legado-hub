package io.legado.app.data.entities

import io.legado.app.model.analyzeRule.RuleDataInterface

open class BaseSource(
    private val values: MutableMap<String, String> = linkedMapOf(),
) {
    var enabledCookieJar: Boolean = false

    open fun get(key: String): String? = values[key]

    open fun put(key: String, value: String): String {
        values[key] = value
        return value
    }

    open fun getTag(): String? = values["tag"]

    open fun getKey(): String? = values["bookSourceUrl"] ?: values["sourceUrl"]

    open fun getHeaderMap(includeAuth: Boolean = true): Map<String, String> = emptyMap()
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
) : BaseBook(variableMap)

class BookSource(values: MutableMap<String, String> = linkedMapOf()) : BaseSource(values)

class BookChapter(
    var title: String = "",
    override val variableMap: HashMap<String, String> = hashMapOf(),
) : RuleDataInterface {
    override fun putBigVariable(key: String, value: String?) = Unit

    override fun getBigVariable(key: String): String? = null
}

class RssArticle(
    override val variableMap: HashMap<String, String> = hashMapOf(),
) : RuleDataInterface {
    override fun putBigVariable(key: String, value: String?) = Unit

    override fun getBigVariable(key: String): String? = null
}
