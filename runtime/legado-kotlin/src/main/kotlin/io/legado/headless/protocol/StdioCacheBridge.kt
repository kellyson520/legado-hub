package io.legado.headless.protocol

import com.google.gson.Gson
import io.legado.headless.ports.CacheBridge
import java.io.BufferedReader
import java.io.PrintWriter
import java.util.UUID

/** Synchronous cache port paired with the native runtime stdio protocol. */
class StdioCacheBridge(
    private val input: BufferedReader,
    private val output: PrintWriter,
    private val gson: Gson = Gson(),
) : CacheBridge {
    override fun get(scope: String, key: String): String? {
        val response = request("get", scope, key, null)
        if (response["found"] != true) return null
        return response["value"]?.toString()
    }

    override fun put(scope: String, key: String, value: String) {
        request("put", scope, key, value)
    }

    override fun delete(scope: String, key: String) {
        request("delete", scope, key, null)
    }

    private fun request(op: String, scope: String, key: String, value: String?): Map<*, *> {
        val id = UUID.randomUUID().toString()
        output.println(
            gson.toJson(
                mapOf(
                    "type" to "bridge_cache",
                    "id" to id,
                    "request" to mapOf(
                        "op" to op,
                        "scope" to scope,
                        "key" to key,
                        "value" to value,
                    ),
                )
            )
        )
        output.flush()

        while (true) {
            val line = input.readLine() ?: throw IllegalStateException("cache bridge input closed")
            val message = gson.fromJson(line, Map::class.java)
            if (message["type"] != "bridge_cache_result" || message["id"] != id) continue
            val response = message["response"] as? Map<*, *> ?: emptyMap<String, Any?>()
            if (response["error_code"] != null) {
                throw IllegalStateException(response["error_code"].toString())
            }
            return response
        }
    }
}
