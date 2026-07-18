package io.legado.app.utils

import com.google.gson.Gson
import com.google.gson.JsonParser
import com.google.gson.reflect.TypeToken
import java.net.URL

open class JsonCodec {
    val gson: Gson = Gson()

    fun toJson(value: Any?): String = gson.toJson(value)
}

object GSON : JsonCodec()

object GSONStrict : JsonCodec()

inline fun <reified T> JsonCodec.fromJsonObject(value: String): Result<T> = runCatching {
    gson.fromJson(value, object : TypeToken<T>() {}.type)
}

inline fun <reified T> JsonCodec.fromJsonArray(value: String): Result<List<T>> = runCatching {
    gson.fromJson(value, object : TypeToken<List<T>>() {}.type)
}

fun <K, V> MutableMap<K, V>.getOrPutLimit(key: K, limit: Int, defaultValue: () -> V): V {
    this[key]?.let { return it }
    while (size >= limit) keys.firstOrNull()?.let(::remove) ?: break
    return defaultValue().also { put(key, it) }
}

fun String.isDataUrl(): Boolean = startsWith("data:", ignoreCase = true)

fun String.isJson(): Boolean = runCatching {
    JsonParser.parseString(trim())
    true
}.getOrDefault(false)

fun String.splitNotBlank(delimiter: String): List<String> =
    split(delimiter).map(String::trim).filter(String::isNotEmpty)

val Throwable.stackTraceStr: String
    get() = stackTraceToString()

fun Throwable.printOnDebug() {
    System.err.println(stackTraceToString())
}

val isMainThread: Boolean = false

object NetworkUtils {
    fun getAbsoluteURL(base: URL?, value: String): String {
        val candidate = value.trim()
        if (candidate.isEmpty()) return ""
        return runCatching {
            if (base == null) URL(candidate).toString() else URL(base, candidate).toString()
        }.getOrDefault(candidate)
    }
}
