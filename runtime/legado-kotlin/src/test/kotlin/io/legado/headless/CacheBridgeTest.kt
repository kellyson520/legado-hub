package io.legado.headless

import io.legado.app.help.CacheManager
import io.legado.headless.ports.HeadlessRuntimeBridges
import io.legado.headless.ports.CacheBridge
import io.legado.headless.ports.MemoryCacheBridge
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import com.google.gson.JsonParser

class CacheBridgeTest {
    @AfterTest
    fun resetBridge() {
        HeadlessRuntimeBridges.cache = null
        CacheManager.clearScope("cache-test")
    }

    @Test
    fun cacheManagerKeepsValuesSeparatedBySourceScope() {
        HeadlessRuntimeBridges.cache = MemoryCacheBridge()

        CacheManager.withScope("cache-test") {
            CacheManager.put("token", "abc")
        }
        CacheManager.withScope("other-source") {
            assertNull(CacheManager.get("token"))
        }

        CacheManager.withScope("cache-test") {
            assertEquals("abc", CacheManager.get("token"))
            CacheManager.delete("token")
            assertNull(CacheManager.get("token"))
        }
    }

    @Test
    fun stdioCacheBridgeRoundTripUsesStableMessageTypes() {
        val input = java.io.BufferedReader(
            java.io.StringReader(
                "{\"type\":\"bridge_cache_result\",\"id\":\"cache-1\",\"response\":{\"found\":true,\"value\":\"abc\"}}\n"
            )
        )
        val output = java.io.StringWriter()
        val bridge = io.legado.headless.protocol.StdioCacheBridge(input, java.io.PrintWriter(output, true))

        assertEquals("abc", bridge.get("cache-test", "token"))
        assertEquals(true, output.toString().contains("bridge_cache"))
    }

    @Test
    fun cacheOperationsAreIncludedInRequestTraceWithoutValues() {
        HeadlessRuntimeBridges.cache = MemoryCacheBridge()
        val response = JsonParser.parseString(
            io.legado.headless.protocol.RuntimeServer().dispatchLine(
                """
                {
                  "id":"cache-trace",
                  "op":"extract_string",
                  "stage":"search",
                  "rule":"@js:cache.put('token', 'secret'); return cache.get('token')",
                  "content":"ignored",
                  "context":{"cacheScope":"source-a"}
                }
                """.trimIndent()
            )
        ).asJsonObject

        val trace = response["trace"].asJsonObject
        assertTrue(trace["cache_events"].asJsonArray.size() >= 2)
        assertFalse(trace.toString().contains("secret"))
    }

    @Test
    fun cacheBridgeFailureFallsBackToScopedMemory() {
        HeadlessRuntimeBridges.cache = object : CacheBridge {
            override fun get(scope: String, key: String): String? = error("bridge down")
            override fun put(scope: String, key: String, value: String) = error("bridge down")
            override fun delete(scope: String, key: String) = error("bridge down")
        }

        CacheManager.withScope("fallback-source") {
            CacheManager.put("token", "local")
            assertEquals("local", CacheManager.get("token"))
        }
    }
}
