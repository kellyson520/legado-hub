package io.legado.headless

import io.legado.app.data.entities.BookSource
import io.legado.headless.ports.HeadlessRuntimeBridges
import io.legado.headless.ports.HttpRequestSpec
import io.legado.headless.ports.HttpResponse
import io.legado.app.model.analyzeRule.AnalyzeUrl
import io.legado.app.help.http.CookieStore
import com.google.gson.JsonParser
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class NativeAnalyzerRequestSemanticsTest {
    private val requests = mutableListOf<HttpRequestSpec>()

    @AfterTest
    fun clearBridge() {
        HeadlessRuntimeBridges.http = null
        CookieStore.removeCookie("https://example.test/")
    }

    @Test
    fun sourceHeadersAreDecodedAndUserAgentIsPreserved() {
        val source = BookSource(
            mutableMapOf(
                "bookSourceUrl" to "https://example.test/",
                "header" to "{\"X-Source\":\"native\",\"User-Agent\":\"lego-test\"}",
            )
        )

        assertEquals("native", source.getHeaderMap()["X-Source"])
        assertEquals("lego-test", source.getHeaderMap()["User-Agent"])
    }

    @Test
    fun analyzeUrlParsesPageHeadersAndPostBodyOptions() {
        HeadlessRuntimeBridges.http = { spec ->
            requests += spec
            HttpResponse(status = 200, body = "ok", finalUrl = spec.url)
        }
        val source = BookSource(mutableMapOf("bookSourceUrl" to "https://example.test/"))
        val analyzeUrl = AnalyzeUrl(
            "https://example.test/p<1,2,3>,{\"method\":\"POST\",\"headers\":{\"X-Mode\":\"native\"},\"body\":\"a=1\"}",
            page = 2,
            source = source,
        )

        val response = analyzeUrl.getStrResponse()

        assertEquals("ok", response.body)
        assertEquals(1, requests.size)
        assertEquals("POST", requests.single().method)
        assertEquals("https://example.test/p2", requests.single().url)
        assertEquals("native", requests.single().headers["X-Mode"])
        assertEquals("a=1", requests.single().body)
    }

    @Test
    fun nativeJavaGetUsesTheSameBridgeAndReturnsAReadableResponse() {
        HeadlessRuntimeBridges.http = { spec ->
            requests += spec
            HttpResponse(status = 200, body = "bridge-ok", finalUrl = spec.url)
        }
        val request = JsonParser.parseString(
            """
            {
              "op":"extract_string",
              "rule":"@js:return java.get('https://example.test/data', {}).body()",
              "content":"ignored"
            }
            """.trimIndent()
        ).asJsonObject

        val result = NativeAnalyzer().execute(request).first

        assertEquals("bridge-ok", result)
        assertEquals("GET", requests.single().method)
        assertTrue(requests.single().url.endsWith("/data"))
    }

    @Test
    fun responseCookiesAreReusedByTheNextRequestForTheSameSource() {
        var count = 0
        HeadlessRuntimeBridges.http = { spec ->
            requests += spec
            count += 1
            if (count == 1) {
                HttpResponse(status = 200, body = "seed", headers = mapOf("Set-Cookie" to "sid=abc; Path=/"))
            } else {
                HttpResponse(status = 200, body = "next")
            }
        }
        val source = BookSource(mutableMapOf("bookSourceUrl" to "https://example.test/"))
        AnalyzeUrl("https://example.test/seed", source = source).getStrResponse()
        AnalyzeUrl("https://example.test/next", source = source).getStrResponse()

        assertEquals("sid=abc", requests[1].headers["Cookie"])
    }

    @Test
    fun runtimeResponseCarriesMutatedRuleContext() {
        val response = io.legado.headless.protocol.RuntimeServer().dispatchLine(
            """
            {
              "id":"ctx-1",
              "op":"extract_string",
              "rule":"@js:java.put('token', 'updated'); return java.get('token')",
              "content":"ignored",
              "context":{"source":{"token":"old"},"variables":{}}
            }
            """.trimIndent()
        )

        assertTrue(response.contains("\"success\":true"))
        assertTrue(response.contains("\"updated\""))
    }
}
