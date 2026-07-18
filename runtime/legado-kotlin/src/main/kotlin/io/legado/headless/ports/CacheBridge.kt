package io.legado.headless.ports

interface CacheBridge {
    fun get(scope: String, key: String): String?

    fun put(scope: String, key: String, value: String)
}

class MemoryCacheBridge : CacheBridge {
    private val values = linkedMapOf<Pair<String, String>, String>()

    override fun get(scope: String, key: String): String? = values[scope to key]

    override fun put(scope: String, key: String, value: String) {
        values[scope to key] = value
    }
}
