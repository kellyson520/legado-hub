package io.legado.headless

import com.google.gson.JsonParser
import kotlin.test.Test
import kotlin.test.assertEquals

class NativeAnalyzerContextTest {
    @Test
    fun nativeRuleReceivesSourceAndBookContext() {
        val request = JsonParser.parseString(
            """
            {
              "op":"extract_string",
              "rule":"@js:return source.get('token') + ':' + bookName",
              "content":"ignored",
              "base_url":"https://example.test/",
              "context":{
                "source":{"token":"abc"},
                "book":{"name":"剑来"},
                "variables":{}
              }
            }
            """.trimIndent()
        ).asJsonObject

        val value = NativeAnalyzer().execute(request).first

        assertEquals("abc:剑来", value)
    }
}
