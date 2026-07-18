package io.legado.headless

import io.legado.app.model.analyzeRule.AnalyzeRule
import kotlin.test.Test
import kotlin.test.assertEquals

class NativeRuleSemanticsTest {
    @Test
    fun cssNegativeIndexAndTextNodesMatchLegado() {
        val html = "<ul><li>A</li><li>B</li><li>C</li></ul>"
        val analyzer = AnalyzeRule().setContent(html, "https://example.test/")
        assertEquals("C", analyzer.getString("ul@li.-1@text"))
        assertEquals(listOf("A", "B", "C"), analyzer.getStringList("ul@li@text"))
    }

    @Test
    fun jsonInnerRulesAndFallbackArePreserved() {
        val json = "{\"items\":[{\"name\":\"A\"}]}"
        val analyzer = AnalyzeRule().setContent(json)
        assertEquals("A", analyzer.getString("$.items[0].name||$.missing"))
    }
}
