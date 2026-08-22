package com.mudaremote.android

import android.content.Context
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * Single serialized entry point for booting the embedded interpreter.
 *
 * Chaquopy's Python.start() is not safe to invoke concurrently from the
 * Activity and Service worker threads; racing calls can crash the process.
 * All callers go through here instead of touching Python.start() directly.
 */
object PythonRuntime {
    @Volatile
    private var bootAttempted = false

    @Synchronized
    fun ensureStarted(context: Context) {
        if (Python.isStarted()) return
        if (bootAttempted && !Python.isStarted()) {
            // A previous attempt failed; allow a retry but keep it serialized.
        }
        bootAttempted = true
        Python.start(AndroidPlatform(context.applicationContext))
    }

    val isStarted: Boolean
        get() = Python.isStarted()
}
