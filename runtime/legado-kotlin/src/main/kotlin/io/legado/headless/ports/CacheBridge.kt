package io.legado.headless.ports

interface CacheBridge {
    fun get(scope: String, key: String): String?

    fun put(scope: String, key: String, value: String)

    fun delete(scope: String, key: String)
}

class MemoryCacheBridge : CacheBridge {
    private val values = linkedMapOf<Pair<String, String>, String>()

    @Synchronized
    override fun get(scope: String, key: String): String? = values[scope to key]

    @Synchronized
    override fun put(scope: String, key: String, value: String) {
        values[scope to key] = value
    }

    @Synchronized
    override fun delete(scope: String, key: String) {
        values.remove(scope to key)
    }

    @Synchronized
    fun clear(scope: String) {
        values.keys.filter { it.first == scope }.toList().forEach(values::remove)
    }
}
