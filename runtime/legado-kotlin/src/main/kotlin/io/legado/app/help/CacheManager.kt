package io.legado.app.help

object CacheManager {
    private val memory = linkedMapOf<String, String>()

    @Synchronized
    fun getFromMemory(key: String): String? = memory[key]

    @Synchronized
    fun putMemory(key: String, value: String) {
        memory[key] = value
    }

    @Synchronized
    fun remove(key: String) {
        memory.remove(key)
    }

    fun get(key: String): String? = getFromMemory(key)

    fun put(key: String, value: Any?, saveTime: Int = 0): String {
        val encoded = value?.toString().orEmpty()
        putMemory(key, encoded)
        return encoded
    }

    fun delete(key: String) = remove(key)
}
