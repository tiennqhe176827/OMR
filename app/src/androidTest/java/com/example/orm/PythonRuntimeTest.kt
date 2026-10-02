package com.example.orm

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Run the installed test APK with am instrument to preserve existing app data. */
@RunWith(AndroidJUnit4::class)
class PythonRuntimeTest {
    @Test fun cv1239TemplateLoadsAndCanBeSelected() {
        val bridge = Python.getInstance().getModule("android_bridge")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val scanner = bridge.callAttr("Scanner", context.cacheDir.resolve("cv1239-runtime").absolutePath)
        assertEquals("cv1239", scanner.callAttr("set_template", "cv1239").toString())
        val template = scanner.get("template_path")!!.toString()
        val loaded = Python.getInstance().getModule("omr.template_loader").callAttr("load_template", template)
        val data = JSONObject(Python.getInstance().getModule("json").callAttr("dumps", loaded.get("data")).toString())
        assertEquals(4, data.getJSONObject("ma_de").getInt("num_columns"))
        assertEquals(8, data.getJSONObject("sbd").getInt("num_columns"))
        assertEquals("current", scanner.callAttr("set_template", "current").toString())
    }

    @Test fun packagedTemplateAndNativeLibrariesLoad() {
        val python = Python.getInstance()
        val bridge = python.getModule("android_bridge")
        val template = bridge.get("TEMPLATE")!!.toString()
        assertNotNull(python.getModule("omr.template_loader").callAttr("load_template", template))
        // Checks the Java signed byte[] -> Python buffer boundary, including 128 and 255.
        val image = bridge.callAttr("camera_image", byteArrayOf(0, -128, -1, 1, -127, -2), 3, 2, 90)
        val rows = JSONObject("{\"pixels\":" + python.getModule("json").callAttr("dumps", image.callAttr("tolist")) + "}")
        assertEquals(3, rows.getJSONArray("pixels").length())
        assertEquals(128, rows.getJSONArray("pixels").getJSONArray(1).getInt(1))
        assertNotNull(python.getModule("camera_tracker").callAttr("SheetTracker"))
        val dir = InstrumentationRegistry.getInstrumentation().targetContext.cacheDir.resolve("runtime-smoke")
        val scanner = bridge.callAttr("Scanner", dir.absolutePath)
        val output = JSONObject(scanner.callAttr("analyze", ByteArray(640 * 480) { -1 }, 640, 480, 0).toString())
        assertEquals("searching", output.getString("state"))
    }

    @Test fun fullResolutionFrameWaitsTwoSecondsAndSurvivesMovement() {
        val width = 1920
        val height = 2560
        val frame = ByteArray(width * height) { 50 }
        for (y in 100 until 2460) for (x in 120 until 1800) frame[y * width + x] = 215.toByte()
        for (y in 200 until 2350 step 50) for (dy in 0..3) for (x in 200 until 1650) frame[(y + dy) * width + x] = 70
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val scanner = Python.getInstance().getModule("android_bridge")
            .callAttr("Scanner", context.cacheDir.resolve("outline-smoke").absolutePath)
        for (timestamp in listOf(0L, 1_000_000_000L)) {
            val waiting = JSONObject(scanner.callAttr("observe_and_capture", frame, width, height, 0, timestamp).toString())
            assertEquals("stabilizing", waiting.getString("state"))
        }
        val started = android.os.SystemClock.elapsedRealtimeNanos()
        val output = JSONObject(scanner.callAttr("observe_and_capture", frame, width, height, 0, 2_000_000_000L).toString())
        val elapsedMs = (android.os.SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0
        assertEquals("captured", output.getString("state"))
        assertEquals(width, output.getJSONObject("capture").getInt("width"))
        assertEquals(height, output.getJSONObject("capture").getInt("height"))
        assertTrue("Retaining 5 MP frame took $elapsedMs ms", elapsedMs < 2000)
        val checksum = scanner.get("captured_frame")!!.callAttr("sum").toString()
        frame.fill(255.toByte())
        val next = JSONObject(scanner.callAttr("observe_and_capture", frame, width, height, 0, 999999L).toString())
        assertEquals(2_000_000_000L, next.getJSONObject("capture").getLong("timestamp_ns"))
        assertEquals(checksum, scanner.get("captured_frame")!!.callAttr("sum").toString())
        val benchmark = JSONObject().put("device", android.os.Build.MODEL)
            .put("test", "synthetic_5mp_detect_and_retain")
            .put("elapsed_ms", elapsedMs).put("capture", output.getJSONObject("capture"))
        context.filesDir.resolve("omr").apply { mkdirs() }.resolve("capture-benchmark.json").writeText(benchmark.toString(2))
        android.util.Log.i("OMRCapture", benchmark.toString())
    }
}
