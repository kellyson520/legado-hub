package androidx.collection

class LruCache<K, V>(private val maxSize: Int) {
    private val values = object : LinkedHashMap<K, V>(maxSize, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<K, V>?): Boolean = size > maxSize
    }

    @Synchronized
    operator fun get(key: K): V? = values[key]

    @Synchronized
    operator fun set(key: K, value: V) {
        values[key] = value
    }

    @Synchronized
    fun put(key: K, value: V): V? = values.put(key, value)

    @Synchronized
    fun remove(key: K): V? = values.remove(key)
}
