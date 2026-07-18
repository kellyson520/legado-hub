package io.legado.headless

import io.legado.headless.protocol.RuntimeServer
import com.google.gson.JsonParser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RuntimeProtocolTest {
    private val server = RuntimeServer()

    @Test
    fun pingReturnsProtocolAndEngineRevision() {
        val response = JsonParser.parseString(
            server.dispatchLine("{\"id\":\"1\",\"op\":\"ping\",\"protocol_version\":1}")
        ).asJsonObject
        assertTrue(response["success"].asBoolean)
        assertEquals("1", response["id"].asString)
        assertEquals(1, response["protocol_version"].asInt)
        assertEquals("legado-kotlin", response["trace"].asJsonObject["engine"].asString)
    }

    @Test
    fun malformedJsonHasStableErrorCode() {
        val response = JsonParser.parseString(server.dispatchLine("not-json")).asJsonObject
        assertFalse(response["success"].asBoolean)
        assertEquals("MALFORMED_REQUEST", response["error"].asJsonObject["code"].asString)
    }

    @Test
    fun traceContainsSafeRequestMetadataWithoutPayloadContents() {
        val response = JsonParser.parseString(
            server.dispatchLine(
                """
                {
                  "id":"trace-1",
                  "op":"extract_string",
                  "stage":"content",
                  "rule":"#content@text",
                  "content":"<div id=\"content\">secret body</div>",
                  "content_type":"html"
                }
                """.trimIndent()
            )
        ).asJsonObject

        val trace = response["trace"].asJsonObject
        assertEquals("content", trace["stage"].asString)
        assertEquals("extract_string", trace["operation"].asString)
        assertEquals("#content@text".length, trace["rule_length"].asInt)
        assertEquals("<div id=\"content\">secret body</div>".length, trace["content_length"].asInt)
        assertEquals("html", trace["content_type"].asString)
        assertFalse(trace.toString().contains("secret body"))
    }
}
