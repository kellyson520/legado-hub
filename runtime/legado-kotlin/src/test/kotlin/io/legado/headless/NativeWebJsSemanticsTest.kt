package io.legado.headless

import io.legado.app.model.analyzeRule.AnalyzeRule
import kotlin.test.Test
import kotlin.test.assertEquals

class NativeWebJsSemanticsTest {
    @Test
    fun webJsCanReadDocumentSelectorsFromTheCurrentHtml() {
        val analyzer = AnalyzeRule().setContent("<html><body><h1>剑来</h1></body></html>")

        val value = analyzer.getString("@webjs:return document.querySelector('h1').textContent")

        assertEquals("剑来", value)
    }
}
