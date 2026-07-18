package io.legado.headless.ports

data class SourceContext(
    val source: Map<String, Any?> = emptyMap(),
    val book: Map<String, Any?> = emptyMap(),
    val chapter: Map<String, Any?> = emptyMap(),
    val variables: MutableMap<String, String> = linkedMapOf(),
    val baseUrl: String? = null,
    val cacheScope: String = "default",
)
