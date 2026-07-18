package io.legado.app.help

import io.legado.headless.ports.HeadlessRuntimeBridges
import io.legado.headless.ports.CacheTraceEvent
import io.legado.headless.ports.RuntimeTraceContext

object CacheManager {
    private val memory = linkedMapOf<String, String>()
    private val scope = ThreadLocal.withInitial { "default" }

    @Synchronized
    fun getFromMemory(key: String): String? = getLocal(scopedKey(key))

    @Synchronized
    fun putMemory(key: String, value: String) {
        putLocal(scopedKey(key), value)
    }

    @Synchronized
    fun remove(key: String) {
        removeLocal(scopedKey(key))
    }

    fun get(key: String): String? {
        val bridge = HeadlessRuntimeBridges.cache
        val scope = currentScope()
        if (bridge == null) {
            return getFromMemory(key).also { value ->
                RuntimeTraceContext.record(CacheTraceEvent("get", scope, key.length, found = value != null))
            }
        }
        return try {
            bridge.get(scope, key).also { value ->
                RuntimeTraceContext.record(CacheTraceEvent("get", scope, key.length, found = value != null))
            }
        } catch (_: Exception) {
            RuntimeTraceContext.record(CacheTraceEvent("get", scope, key.length, errorCode = "CACHE_BRIDGE_ERROR"))
            getFromMemory(key)
        }
    }

    fun put(key: String, value: Any?, saveTime: Int = 0): String {
        val encoded = value?.toString().orEmpty()
        val bridge = HeadlessRuntimeBridges.cache
        val scope = currentScope()
        if (bridge == null) {
            putMemory(key, encoded)
            RuntimeTraceContext.record(CacheTraceEvent("put", scope, key.length, changed = true))
            return encoded
        }
        try {
            bridge.put(scope, key, encoded)
            RuntimeTraceContext.record(CacheTraceEvent("put", scope, key.length, changed = true))
        } catch (_: Exception) {
            RuntimeTraceContext.record(CacheTraceEvent("put", scope, key.length, changed = false, errorCode = "CACHE_BRIDGE_ERROR"))
            putMemory(key, encoded)
        }
        return encoded
    }

    fun delete(key: String) {
        val bridge = HeadlessRuntimeBridges.cache
        val scope = currentScope()
        if (bridge == null) {
            remove(key)
            RuntimeTraceContext.record(CacheTraceEvent("delete", scope, key.length, changed = true))
            return
        }
        try {
            bridge.delete(scope, key)
            RuntimeTraceContext.record(CacheTraceEvent("delete", scope, key.length, changed = true))
        } catch (_: Exception) {
            RuntimeTraceContext.record(CacheTraceEvent("delete", scope, key.length, changed = false, errorCode = "CACHE_BRIDGE_ERROR"))
            remove(key)
        }
    }

    fun currentScope(): String = scope.get()

    fun <T> withScope(value: String?, block: () -> T): T {
        val previous = currentScope()
        scope.set(value?.ifBlank { "default" } ?: "default")
        return try {
            block()
        } finally {
            scope.set(previous)
        }
    }

    @Synchronized
    fun clearScope(value: String) {
        val prefix = "$value\u0000"
        memory.keys.filter { it.startsWith(prefix) }.toList().forEach(memory::remove)
        (HeadlessRuntimeBridges.cache as? io.legado.headless.ports.MemoryCacheBridge)?.clear(value)
    }

    private fun scopedKey(key: String): String = "${currentScope()}\u0000$key"

    private fun getLocal(key: String): String? = memory[key]

    private fun putLocal(key: String, value: String) {
        memory[key] = value
    }

    private fun removeLocal(key: String) {
        memory.remove(key)
    }
}
