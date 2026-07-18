package io.legado.headless

import io.legado.headless.protocol.StdioHttpBridge
import java.io.BufferedReader
import java.io.StringReader
import java.io.StringWriter
import java.io.PrintWriter
import kotlin.test.Test
import kotlin.test.assertEquals

class StdioBridgeTest {
    @Test
    fun bridgeRoundTripUsesNestedJsonMessage() {
        val input = BufferedReader(
            StringReader(
                "{\"type\":\"bridge_http_result\",\"id\":\"bridge-1\",\"response\":{\"status\":200,\"body\":\"ok\"}}\n"
            )
        )
        val output = StringWriter()
        val bridge = StdioHttpBridge(input, PrintWriter(output, true))

        val response = bridge.request(
            io.legado.headless.ports.HttpRequestSpec(method = "GET", url = "https://example.test")
        )

        assertEquals(200, response.status)
        assertEquals("ok", response.body)
        assertEquals(true, output.toString().contains("bridge_http"))
    }
}
