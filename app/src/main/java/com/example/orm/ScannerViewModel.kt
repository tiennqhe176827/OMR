package com.example.orm

import android.app.Application
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import androidx.camera.core.ImageProxy
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

class ScannerViewModel(app: Application) : AndroidViewModel(app) {
    val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val generation = AtomicInteger()
    private lateinit var bridge: PyObject
    private lateinit var scanner: PyObject
    val directory = File(app.filesDir, "omr").apply { mkdirs() }
    var ready by mutableStateOf(false); private set
    var busy by mutableStateOf(false); private set
    var message by mutableStateOf("Đang khởi tạo bộ đọc OMR…")
    var result by mutableStateOf<JSONObject?>(null); private set
    var gridPath by mutableStateOf<String?>(null); private set
    var capturedPreview by mutableStateOf<Bitmap?>(null); private set
    var exam by mutableStateOf("")
    var subject by mutableStateOf("Toán")
    var track by mutableStateOf("Khoa học máy tính")
    var code by mutableStateOf("")
    var keyText by mutableStateOf<String?>(null)
    var keyRevision = -1
    var pendingExport = ""
    var diagnosticPath: String? = null; private set
    var diagnosticStatus by mutableStateOf(""); private set
    @Volatile var scanning = false
    @Volatile private var manualRequested = false
    var manualPending by mutableStateOf(false); private set
    private val isProcessing = java.util.concurrent.atomic.AtomicBoolean(false)
    private var yBuffer: ByteArray? = null
    var overlayCorners by mutableStateOf<List<Float>?>(null); private set
    var overlayHits by mutableStateOf<List<Float?>>(emptyList()); private set
    var overlayState by mutableStateOf(""); private set
    var overlayAspect by mutableStateOf(0f); private set
    private val prefs = app.getSharedPreferences("scan", 0)
    var sheetTemplate by mutableStateOf(prefs.getString("sheet_template", "current") ?: "current"); private set

    init {
        exam = prefs.getString("exam", "Bài kiểm tra 1")!!
        subject = prefs.getString("subject", "Toán")!!
        track = prefs.getString("track", "Khoa học máy tính")!!
        worker.execute {
            try {
                bridge = Python.getInstance().getModule("android_bridge")
                scanner = bridge.callAttr("Scanner", directory.absolutePath)
                scanner.callAttr("set_template", sheetTemplate)
                main.post { ready = true; scanning = true; message = "Đưa toàn bộ phiếu vào camera." }
            } catch (e: Exception) { main.post { message = "Không khởi tạo được OMR: ${e.message}" } }
        }
    }

    fun pause() {
        scanning = false; manualRequested = false; manualPending = false
        worker.execute { if (ready) scanner.callAttr("cancel_pending_capture") }
        // A frozen photo can finish processing after the user lowers/locks the phone.
        if (capturedPreview == null) generation.incrementAndGet()
    }

    fun readNow() {
        if (!ready || busy || manualPending || capturedPreview != null) return
        manualRequested = true
        manualPending = true
        scanning = true
        diagnosticStatus = ""
        message = "Đang lấy khung camera để đọc phiếu…"
    }

    fun selectSheetTemplate(id: String) {
        if (!ready || busy || id == sheetTemplate || id !in listOf("current", "cv1239")) return
        pause()
        busy = true
        worker.execute {
            try {
                scanner.callAttr("set_template", id)
                main.post {
                    sheetTemplate = id
                    prefs.edit().putString("sheet_template", id).apply()
                    reset()
                }
            } catch (e: Exception) {
                main.post { busy = false; message = "Không tải được mẫu phiếu: ${e.message}" }
            }
        }
    }

    fun reset() {
        pause()
        generation.incrementAndGet()
        busy = false
        result = null; gridPath = null
        capturedPreview = null
        diagnosticStatus = ""
        overlayCorners = null
        overlayHits = emptyList()
        overlayState = ""
        overlayAspect = 0f
        captureTriggered = false
        message = "Đưa toàn bộ phiếu vào camera."
        val token = generation.get()
        worker.execute {
            if (ready) scanner.callAttr("reset")
            main.post { if (generation.get() == token) scanning = ready }
        }
    }

    @Volatile private var captureTriggered = false

    /** Runs on CameraX's single analysis executor. Always releases its ImageProxy. */
    fun analyze(frame: ImageProxy) {
        if (!isProcessing.compareAndSet(false, true)) {
            frame.close()
            return
        }
        try {
            if (!scanning || !ready) return
            val began = SystemClock.elapsedRealtimeNanos()
            val token = generation.get()
            val manual = manualRequested
            if (manual) manualRequested = false

            val plane = frame.planes[0]
            val buffer = plane.buffer.duplicate()
            val base = buffer.position()
            // ViewPort gives Preview and Analysis the same sensor crop. Pack only
            // that crop so Python coordinates map directly onto PreviewView.
            val crop = frame.cropRect
            val cropWidth = crop.width()
            val cropHeight = crop.height()
            val size = cropWidth * cropHeight
            if (yBuffer == null || yBuffer!!.size != size) yBuffer = ByteArray(size)
            val packed = yBuffer!!
            for (y in 0 until cropHeight) {
                val row = base + (crop.top + y) * plane.rowStride + crop.left * plane.pixelStride
                if (plane.pixelStride == 1) {
                    buffer.position(row)
                    buffer.get(packed, y * cropWidth, cropWidth)
                } else {
                    for (x in 0 until cropWidth) packed[y * cropWidth + x] = buffer.get(row + x * plane.pixelStride)
                }
            }
            // Python owns a full-resolution copy before it returns "captured".
            // There is no second exposure or asynchronous still-camera callback.
            val response = JSONObject(scanner.callAttr("observe_and_capture", packed, cropWidth, cropHeight,
                frame.imageInfo.rotationDegrees, frame.imageInfo.timestamp, manual).toString())
            val state = response.optString("state", "")
            val shouldCapture = state == "captured" && !captureTriggered
            val frozenPreview = if (shouldCapture) {
                BitmapFactory.decodeFile(response.getString("preview_path"))
                    ?: error("Không mở được ảnh vừa giữ.")
            } else null
            if (shouldCapture) {
                captureTriggered = true
                scanning = false
            }
            val frameAspect = if (frame.imageInfo.rotationDegrees % 180 == 0)
                cropWidth.toFloat() / cropHeight else cropHeight.toFloat() / cropWidth

            main.post {
                if (token != generation.get()) return@post
                message = response.optString("message", message)
                overlayState = state
                overlayAspect = frameAspect
                val cornersOpt = response.optJSONArray("corners")
                val hitsOpt = response.optJSONArray("corner_hits")
                overlayHits = if (hitsOpt != null && hitsOpt.length() == 4) {
                    buildList {
                        for (i in 0 until 4) {
                            val point = hitsOpt.optJSONArray(i)
                            add(point?.optDouble(0)?.toFloat())
                            add(point?.optDouble(1)?.toFloat())
                        }
                    }
                } else emptyList()
                if (cornersOpt != null && cornersOpt.length() == 4) {
                    val list = mutableListOf<Float>()
                    for (i in 0 until 4) {
                        val pt = cornersOpt.optJSONArray(i)
                        if (pt != null && pt.length() == 2) {
                            list.add(pt.optDouble(0).toFloat())
                            list.add(pt.optDouble(1).toFloat())
                        }
                    }
                    if (list.size == 8) overlayCorners = list else overlayCorners = null
                } else {
                    overlayCorners = null
                }
                if (shouldCapture) {
                    overlayState = "captured"
                    diagnosticStatus = ""
                    busy = true
                    manualPending = false
                    capturedPreview = frozenPreview
                    message = "Đã giữ ảnh — bạn có thể di chuyển máy. Đang đọc phiếu…"
                    val latency = (SystemClock.elapsedRealtimeNanos() - began) / 1_000_000.0
                    android.util.Log.i("OMRCapture", "frozen_ui_ms=$latency size=${cropWidth}x${cropHeight}")
                }
            }
            if (shouldCapture) worker.execute {
                if (token == generation.get()) processCaptured(token)
            }
        } catch (e: Exception) {
            scanning = false
            main.post { manualPending = false; message = "Gặp lỗi: ${e.message}. Bấm Quét lại để thử lại." }
        } finally {
            frame.close()
            isProcessing.set(false)
        }
    }

    /** Process only the owned frame; camera movement cannot change these pixels. */
    private fun processCaptured(token: Int) {
        try {
            val response = JSONObject(scanner.callAttr("analyze_captured").toString())
            main.post {
                if (token != generation.get()) return@post
                busy = false
                manualPending = false; scanning = false
                message = response.optString("message", message)
                val error = response.opt("error")
                diagnosticStatus = when (error) {
                    is JSONObject -> error.optString("code") + ": " + error.optString("message")
                    is String -> error
                    else -> ""
                }
                if (response.optString("state") == "result") {
                    scanning = false
                    result = response.getJSONObject("result")
                    gridPath = response.getString("grid_path")
                    message = "Đã đọc phiếu. Kiểm tra các ô chưa rõ trước khi dùng kết quả."
                    grade()
                } else {
                    captureTriggered = false
                    overlayState = "searching"
                    overlayCorners = null
                    overlayHits = emptyList()
                    scanning = false
                    message += " Căn lại rồi bấm Quét lại."
                }
            }
        } catch (e: Exception) {
            main.post {
                if (token == generation.get()) {
                    captureTriggered = false
                    manualPending = false
                    busy = false
                    scanning = false
                    message = "Không đọc được ảnh đã giữ: ${e.message}. Bấm Quét lại để chụp lại."
                }
            }
        }
    }

    fun grade() {
        val snapshot = result ?: return
        prefs.edit().putString("exam", exam).putString("subject", subject).putString("track", track).apply()
        val text = JSONObject(snapshot.toString()).apply { remove("grading") }.toString()
        result = JSONObject(text)
        call("grade_result", directory.absolutePath, text, exam, subject, track) { result = JSONObject(it) }
    }

    fun correctAnswer(section: String, question: String, answers: JSONObject, onSaved: () -> Unit) {
        val snapshot = result ?: return
        call("correct_result", directory.absolutePath, snapshot.toString(), section, question,
            answers.toString(), exam, subject, track) {
            result = JSONObject(it)
            message = "Đã lưu bài làm nhập tay và chấm lại."
            onSaved()
        }
    }

    fun prepareDiagnostic(onReady: () -> Unit) {
        if (!ready || busy) return
        pause()
        busy = true
        val device = JSONObject().put("model", android.os.Build.MODEL)
            .put("manufacturer", android.os.Build.MANUFACTURER)
            .put("sdk", android.os.Build.VERSION.SDK_INT).toString()
        worker.execute {
            try {
                val path = scanner.callAttr("diagnostic", device).toString()
                main.post { diagnosticPath = path; busy = false; onReady() }
            } catch (e: Exception) {
                main.post { busy = false; message = "Không xuất được chẩn đoán: ${e.message}. Bấm Quét lại để tiếp tục." }
            }
        }
    }

    fun editKey(load: Boolean) {
        pause()
        if (load) call("load_key", directory.absolutePath, exam, subject, code, track) {
            if (it == "null") message = "Chưa có đáp án cho mã này. Bấm Tạo đáp án."
            else { keyRevision = JSONObject(it).getInt("revision"); keyText = it }
        } else call("key_skeleton", exam, subject, code, track) { keyRevision = -1; keyText = it }
    }

    fun saveKey() {
        val text = keyText ?: return
        call("save_key", directory.absolutePath, text, keyRevision) {
            keyText = null
            message = "Đã lưu đáp án mã ${JSONObject(it).getString("code")}."
            if (result != null) grade()
        }
    }

    fun importKey(text: String) {
        pause()
        call("validate_key_json", text) {
            val key = JSONObject(it)
            exam = key.getString("exam"); subject = key.getString("subject")
            code = key.getString("code")
            if (subject == "Tin học") track = key.getString("track")
            keyRevision = -1; keyText = it
            message = "Kiểm tra đáp án đã nhập rồi bấm Lưu. Mã có sẵn cần được tải trước khi sửa."
        }
    }

    fun history(): List<File> = File(directory, "scans").listFiles()
        ?.filter { it.extension == "json" }?.sortedByDescending { it.name } ?: emptyList()

    fun openScan(file: File) {
        pause()
        busy = true
        worker.execute {
            try {
                val json = JSONObject(file.readText())
                val grid = File(file.parentFile, "${file.nameWithoutExtension}_grid.png")
                main.post { result = json; gridPath = grid.absolutePath; busy = false; grade() }
            } catch (e: Exception) { main.post { busy = false; message = "Không đọc được phiếu: ${e.message}" } }
        }
    }

    private fun call(name: String, vararg args: Any, onSuccess: (String) -> Unit) {
        if (!ready || busy) return
        busy = true
        worker.execute {
            try {
                val value = bridge.callAttr(name, *args).toString()
                main.post { busy = false; onSuccess(value) }
            } catch (e: Exception) { main.post { busy = false; message = e.message ?: "Không xử lý được yêu cầu." } }
        }
    }

    override fun onCleared() { pause(); worker.shutdown() }
}
