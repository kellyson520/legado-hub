package io.legado.app.help.source

import io.legado.app.data.entities.BaseSource
import org.mozilla.javascript.Scriptable
import kotlin.coroutines.CoroutineContext

fun BaseSource.getShareScope(context: CoroutineContext): Scriptable? = null
