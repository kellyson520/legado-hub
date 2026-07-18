package io.legado.headless

import io.legado.app.model.analyzeRule.AnalyzeRule
import io.legado.app.data.entities.Book
import io.legado.app.data.entities.BookChapter
import io.legado.app.data.entities.BookSource
import io.legado.app.help.CacheManager
import io.legado.app.model.analyzeRule.RuleData
import io.legado.app.utils.NetworkUtils
import io.legado.headless.protocol.RuntimeError
import com.google.gson.JsonObject
import com.google.gson.Gson
import java.net.URL

class NativeAnalyzer {
    fun execute(request: JsonObject): Pair<Any?, String?> {
        val operation = request.string("op")
        val rule = request.string("rule")
        val content = request["content"]?.takeUnless { it.isJsonNull }?.let {
            if (it.isJsonPrimitive) it.asString else it.toString()
        } ?: ""
        val context = request["context"]?.takeUnless { it.isJsonNull }?.asJsonObject
        val sourceValues = context?.objectMap("source").toStringMap()
        val bookValues = context?.objectMap("book").toStringMap()
        val chapterValues = context?.objectMap("chapter").toStringMap()
        val variables = context?.objectMap("variables").toStringMap()
        val source = BookSource(sourceValues.toMutableMap())
        val sharedVariables = HashMap(variables)
        val book = Book(
            name = bookValues["name"].orEmpty().ifBlank { context?.stringOrNull("bookName").orEmpty() },
            author = bookValues["author"].orEmpty(),
            variableMap = sharedVariables,
        )
        book.bookUrl = bookValues["bookUrl"].orEmpty()
        book.tocUrl = bookValues["tocUrl"].orEmpty()
        book.coverUrl = bookValues["coverUrl"].orEmpty()
        val chapter = BookChapter(
            title = chapterValues["title"].orEmpty().ifBlank { context?.stringOrNull("title").orEmpty() },
            variableMap = sharedVariables,
        )
        chapter.url = chapterValues["url"].orEmpty()
        chapter.index = chapterValues["index"]?.toIntOrNull() ?: 0
        val ruleData = if (bookValues.isNotEmpty() || variables.isNotEmpty()) {
            book
        } else {
            RuleData()
        }
        val analyzer = AnalyzeRule(ruleData = ruleData, source = source)
            .setChapter(chapter)
            .setContent(content, request.stringOrNull("base_url"))
        request.stringOrNull("redirect_url")?.let(analyzer::setRedirectUrl)

        val cacheScope = context?.stringOrNull("cacheScope") ?: source.getKey().orEmpty()
        val result = CacheManager.withScope(cacheScope) {
            when (operation) {
                "extract_string" -> analyzer.getString(rule) to "string"
                "extract_list" -> analyzer.getStringList(rule).orEmpty() to "list"
                "extract_elements" -> analyzer.getElements(rule).map { it.toString() } to "list"
                "resolve_url" -> {
                    val base = request.stringOrNull("redirect_url") ?: request.stringOrNull("base_url")
                    val parsedBase = base?.let { runCatching { URL(it) }.getOrNull() }
                    NetworkUtils.getAbsoluteURL(parsedBase, rule) to "string"
                }
                else -> throw RuntimeFailure(
                    RuntimeError("UNSUPPORTED_OPERATION", "Unsupported runtime operation: $operation")
                )
            }
        }
        context?.let {
            syncContext(it, source, book, chapter, sharedVariables)
        }
        return result
    }
}

internal class RuntimeFailure(val runtimeError: RuntimeError) : RuntimeException(runtimeError.message)

internal fun JsonObject.string(name: String): String =
    get(name)?.takeUnless { it.isJsonNull }?.asString.orEmpty()

internal fun JsonObject.stringOrNull(name: String): String? =
    get(name)?.takeUnless { it.isJsonNull }?.asString?.takeIf(String::isNotEmpty)

private fun JsonObject?.objectMap(name: String): Map<String, Any?>? =
    this?.get(name)?.takeUnless { it.isJsonNull }?.asJsonObject?.let { Gson().fromJson(it, Map::class.java) as? Map<String, Any?> }

private fun Map<String, Any?>?.toStringMap(): Map<String, String> =
    this.orEmpty().mapValues { (_, value) ->
        when (value) {
            is Map<*, *>, is List<*> -> Gson().toJson(value)
            else -> value?.toString().orEmpty()
        }
    }

private fun syncContext(
    context: JsonObject,
    source: BookSource,
    book: Book,
    chapter: BookChapter,
    variables: Map<String, String>,
) {
    val sourceObject = context.getAsJsonObject("source") ?: JsonObject().also { context.add("source", it) }
    source.values().forEach { (key, value) -> sourceObject.addProperty(key, value) }
    val bookObject = context.getAsJsonObject("book") ?: JsonObject().also { context.add("book", it) }
    bookObject.addProperty("name", book.name)
    bookObject.addProperty("author", book.author)
    bookObject.addProperty("bookUrl", book.bookUrl)
    bookObject.addProperty("tocUrl", book.tocUrl)
    bookObject.addProperty("coverUrl", book.coverUrl)
    val chapterObject = context.getAsJsonObject("chapter") ?: JsonObject().also { context.add("chapter", it) }
    chapterObject.addProperty("title", chapter.title)
    chapterObject.addProperty("url", chapter.url)
    chapterObject.addProperty("index", chapter.index)
    val variableObject = JsonObject()
    variables.forEach { (key, value) -> variableObject.addProperty(key, value) }
    context.add("variables", variableObject)
}
