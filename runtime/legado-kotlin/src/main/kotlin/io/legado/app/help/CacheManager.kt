package io.legado.app.help

object CacheManager {
    private val memory = linkedMapOf<String, String>()

    fun getFromMemory(key: String): String? = memory[key]

    fun putMemory(key: String, value: String) {
        memory[key] = value
    }

    fun remove(key: String) {
        memory.remove(key)
    }
}
