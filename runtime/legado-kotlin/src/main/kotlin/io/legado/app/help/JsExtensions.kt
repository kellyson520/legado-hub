package io.legado.app.help

import io.legado.app.data.entities.BaseSource

interface JsExtensions {
    fun getSource(): BaseSource?
    fun getTag(): String?
    fun ajax(url: Any): String?
    fun ajax(url: Any, callTimeout: Long?): String?
}
