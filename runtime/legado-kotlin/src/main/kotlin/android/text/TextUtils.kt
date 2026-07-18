package android.text

object TextUtils {
    @JvmStatic
    fun isEmpty(value: CharSequence?): Boolean = value == null || value.isEmpty()

    @JvmStatic
    fun join(delimiter: CharSequence, tokens: Iterable<*>): String =
        tokens.joinToString(delimiter.toString())
}
