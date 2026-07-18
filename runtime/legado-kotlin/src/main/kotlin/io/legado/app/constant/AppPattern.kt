package io.legado.app.constant

import java.util.regex.Pattern

object AppPattern {
    val JS_PATTERN: Pattern =
        Pattern.compile("<js>([\\w\\W]*?)</js>|@js:([\\w\\W]*)", Pattern.CASE_INSENSITIVE)
    val WebJS_PATTERN: Pattern =
        Pattern.compile("@webjs:([\\w\\W]{5,})", Pattern.CASE_INSENSITIVE)
}
