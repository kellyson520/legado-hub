package io.legado.headless

import io.legado.app.help.CacheManager
import io.legado.headless.ports.HeadlessRuntimeBridges
import io.legado.headless.ports.MemoryCacheBridge
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

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
}
