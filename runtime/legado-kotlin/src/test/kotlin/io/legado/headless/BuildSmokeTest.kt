package io.legado.headless

import kotlin.test.Test
import kotlin.test.assertNotNull

class BuildSmokeTest {
    @Test
    fun mainClassIsPresent() {
        assertNotNull(Class.forName("io.legado.headless.MainKt"))
    }
}
