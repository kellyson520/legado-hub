package io.legado.headless

import io.legado.headless.protocol.RuntimeServer
import com.google.gson.JsonParser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RuntimeServerTest {
    @Test
    fun extractListReturnsNativeTextValues() {
        val request = """
            {
              "id":"extract-1",
              "op":"extract_list",
              "protocol_version":1,
              "rule":"ul@li@text",
              "content":"<ul><li>A</li><li>B</li></ul>",
              "content_type":"html",
              "base_url":"https://example.test/"
            }
        """.trimIndent()
        val response = JsonParser.parseString(RuntimeServer().dispatchLine(request)).asJsonObject
        assertTrue(response["success"].asBoolean)
        assertEquals("list", response["value_type"].asString)
        assertEquals(listOf("A", "B"), response["value"].asJsonArray.map { it.asString })
    }
}
