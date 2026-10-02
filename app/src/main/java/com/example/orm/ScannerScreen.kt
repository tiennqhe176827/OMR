package com.example.orm

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.Settings
import android.view.MotionEvent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.FocusMeteringAction
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.core.UseCaseGroup
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

val subjects = listOf("Toán", "Ngoại ngữ", "Vật lí", "Hóa học", "Sinh học", "Lịch sử", "Địa lí", "GDKT&PL", "Công nghệ", "Tin học")

@Composable
fun ScannerApp(vm: ScannerViewModel = viewModel()) {
    val context = LocalContext.current
    var tab by rememberSaveable { mutableStateOf(0) }
    var permission by remember { mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
    var requested by rememberSaveable { mutableStateOf(false) }
    val request = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { permission = it; requested = true }
    val diagnosticExport = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
        val path = vm.diagnosticPath
        if (uri != null && path != null) vm.worker.execute {
            try {
                context.contentResolver.openOutputStream(uri)?.use { output -> java.io.File(path).inputStream().use { it.copyTo(output) } }
                    ?: error("Không mở được nơi lưu")
                android.os.Handler(context.mainLooper).post { vm.message = "Đã xuất chẩn đoán gồm khung camera và vị trí marker. Bấm Quét lại để tiếp tục." }
            } catch (e: Exception) { android.os.Handler(context.mainLooper).post { vm.message = "Lỗi xuất chẩn đoán: ${e.message}" } }
        }
    }
    val export = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        val snapshot = vm.pendingExport
        if (uri != null) vm.worker.execute {
            try {
                context.contentResolver.openOutputStream(uri)?.use { it.write(snapshot.toByteArray(Charsets.UTF_8)) } ?: error("Không mở được nơi lưu")
                android.os.Handler(context.mainLooper).post { vm.message = "Đã xuất JSON." }
            } catch (e: Exception) { android.os.Handler(context.mainLooper).post { vm.message = "Lỗi xuất: ${e.message}" } }
        }
    }
    val import = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) vm.worker.execute {
            try {
                val text = context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() } ?: error("Không đọc được file")
                android.os.Handler(context.mainLooper).post { vm.importKey(text) }
            } catch (e: Exception) { android.os.Handler(context.mainLooper).post { vm.message = "Lỗi nhập: ${e.message}" } }
        }
    }
    val owner = LocalLifecycleOwner.current
    val currentTab by rememberUpdatedState(tab)
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) vm.pause()
            if (event == Lifecycle.Event.ON_START) {
                permission = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
                if (currentTab == 0 && vm.result == null && vm.keyText == null &&
                    vm.capturedPreview == null && !vm.busy) vm.reset()
            }
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    Scaffold { padding ->
        Column(Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp)) {
            Text("OMR • Camera 1.17", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(vertical = 4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("Quét phiếu", "Đáp án", "Lịch sử").forEachIndexed { index, title ->
                    FilterChip(selected = tab == index, enabled = !vm.busy && vm.ready,
                        onClick = { tab = index; vm.pause(); if (index == 0 && vm.result == null) vm.reset() }, label = { Text(title) })
                }
            }
            Text(vm.message, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 8.dp))
            if (vm.busy || !vm.ready) LinearProgressIndicator(Modifier.fillMaxWidth())
            when (tab) {
                0 -> if (vm.result != null) {
                    ResultPanel(vm, Modifier.weight(1f), onExport = {
                        vm.pendingExport = vm.result!!.toString(2); export.launch("omr-${System.currentTimeMillis()}.json")
                    })
                } else {
                    val sheetNames = mapOf("current" to "Mẫu phiếu hiện tại", "cv1239" to "THPT CV 1239 • mã đề 4 số")
                    ChoiceMenu(sheetNames[vm.sheetTemplate] ?: sheetNames.getValue("current"), sheetNames.values.toList(), vm.ready && !vm.busy) { name ->
                        vm.selectSheetTemplate(sheetNames.entries.first { it.value == name }.key)
                    }
                    val frozen = vm.capturedPreview
                    if (frozen != null) Image(frozen.asImageBitmap(), contentDescription = "Ảnh phiếu đã giữ",
                        contentScale = ContentScale.Fit,
                        modifier = Modifier.weight(1f).fillMaxWidth().background(Color.Black))
                    else if (permission && vm.ready) CameraPanel(vm, Modifier.weight(1f))
                    else Column(Modifier.weight(1f), verticalArrangement = Arrangement.Center) {
                        Text("Cho phép camera để đọc trực tiếp phiếu trả lời.")
                        Button(onClick = { request.launch(Manifest.permission.CAMERA) }) { Text("Cho phép camera") }
                        if (requested) TextButton(onClick = {
                            context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}")))
                        }) { Text("Mở cài đặt quyền") }
                    }
                    Text(if (frozen == null) "A4 • Đưa máy gần để mép giấy sát khung xanh."
                         else "Ảnh đã cố định. Bạn không cần giữ điện thoại.",
                         style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 4.dp))
                    if (vm.diagnosticStatus.isNotEmpty()) Text(vm.diagnosticStatus, style = MaterialTheme.typography.bodySmall, maxLines = 2)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = vm::readNow, enabled = vm.ready && !vm.busy && !vm.manualPending && permission && frozen == null) { Text(if (vm.manualPending) "Đang giữ ảnh…" else "Chụp ngay") }
                        OutlinedButton(onClick = { vm.reset() }, enabled = vm.ready && !vm.busy) { Text("Quét lại") }
                    }
                    Row {
                        TextButton(onClick = { vm.prepareDiagnostic { diagnosticExport.launch("omr-camera-diagnostic.zip") } }, enabled = vm.ready && !vm.busy && permission) { Text("Xuất chẩn đoán") }
                    }
                }
                1 -> LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    item { ContextFields(vm) }
                    item { OutlinedTextField(vm.code, { vm.code = it.filter(Char::isDigit).take(16) }, label = { Text("Mã đề (giữ số 0 đầu)") }, singleLine = true, enabled = !vm.busy) }
                    item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { vm.editKey(false) }, enabled = vm.ready && !vm.busy && vm.exam.isNotBlank() && vm.code.isNotBlank()) { Text("Tạo đáp án") }
                        OutlinedButton(onClick = { vm.editKey(true) }, enabled = vm.ready && !vm.busy && vm.code.isNotBlank()) { Text("Tải để sửa") }
                    } }
                    item { OutlinedButton(onClick = { import.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) }, enabled = !vm.busy && vm.ready) { Text("Nhập đáp án JSON từ bản máy tính") } }
                    item { Text("Đáp án được lưu riêng theo bài kiểm tra, môn, mã đề và định hướng. Không lấy bài làm làm đáp án đúng tự động.") }
                }
                2 -> {
                    val files = remember(tab, vm.result) { vm.history() }
                    LazyColumn(Modifier.weight(1f)) {
                        if (files.isEmpty()) item { Text("Chưa có phiếu đã quét.") }
                        items(files, key = { it.name }) { file ->
                            TextButton(onClick = { vm.openScan(file); tab = 0 }, enabled = !vm.busy) {
                                Text("Phiếu • ${java.text.DateFormat.getDateTimeInstance().format(java.util.Date(file.lastModified()))}")
                            }
                        }
                    }
                }
            }
        }
    }
    if (vm.keyText != null) KeyEditor(vm, onExport = { vm.pendingExport = vm.keyText!!; export.launch("dap-an-${vm.code}.json") })
}

@Composable
fun ContextFields(vm: ScannerViewModel, onChange: () -> Unit = { vm.grade() }) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(vm.exam, { vm.exam = it; onChange() }, label = { Text("Bài kiểm tra") }, singleLine = true, enabled = !vm.busy, modifier = Modifier.fillMaxWidth())
        ChoiceMenu(vm.subject, subjects, !vm.busy) { vm.subject = it; onChange() }
        if (vm.subject == "Tin học") ChoiceMenu(vm.track, listOf("Khoa học máy tính", "Tin học ứng dụng"), !vm.busy) { vm.track = it; onChange() }
    }
}

@Composable
fun ChoiceMenu(value: String, options: List<String>, enabled: Boolean, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { expanded = true }, enabled = enabled) { Text("$value ▾") }
        DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option -> DropdownMenuItem(text = { Text(option) }, onClick = { expanded = false; onSelect(option) }) }
        }
    }
}

@Suppress("DEPRECATION")
@Composable
fun CameraPanel(vm: ScannerViewModel, modifier: Modifier) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val previewView = remember { PreviewView(context).apply {
        implementationMode = PreviewView.ImplementationMode.COMPATIBLE
        scaleType = PreviewView.ScaleType.FIT_CENTER
    } }
    var camera by remember { mutableStateOf<Camera?>(null) }
    var torch by rememberSaveable { mutableStateOf(false) }
    DisposableEffect(owner, previewView) {
        val future = ProcessCameraProvider.getInstance(context)
        var disposed = false
        var provider: ProcessCameraProvider? = null
        val preview = Preview.Builder().build().also { it.surfaceProvider = previewView.surfaceProvider }
        val analysis = CameraScanConfig.analysis()
        analysis.setAnalyzer(vm.worker, vm::analyze)
        future.addListener({
            previewView.post {
                if (!disposed) try {
                    provider = future.get()
                    val viewPort = previewView.viewPort
                        ?: error("Camera chưa đo được khung xem")
                    val group = UseCaseGroup.Builder()
                        .addUseCase(preview)
                        .addUseCase(analysis)
                        .setViewPort(viewPort)
                        .build()
                    camera = provider!!.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, group)
                    camera?.cameraControl?.setZoomRatio(1f)
                    android.util.Log.i("OMRCapture", "analysis_resolution=${analysis.resolutionInfo?.resolution}; zoom=1.0")
                    previewView.setOnTouchListener { view, event ->
                        if (event.action == MotionEvent.ACTION_UP) {
                            view.performClick()
                            val point = previewView.meteringPointFactory.createPoint(event.x, event.y)
                            camera?.cameraControl?.startFocusAndMetering(FocusMeteringAction.Builder(point).build())
                        }
                        true
                    }
                } catch (e: Exception) { vm.message = "Không mở được camera sau: ${e.message}" }
            }
        }, ContextCompat.getMainExecutor(context))
        onDispose {
            disposed = true
            analysis.clearAnalyzer()
            camera?.cameraControl?.enableTorch(false)
            provider?.unbind(preview, analysis)
            camera = null
        }
    }
    LaunchedEffect(camera, torch) { camera?.cameraControl?.enableTorch(torch) }
    Column(modifier) {
        BoxWithConstraints(Modifier.weight(1f).fillMaxWidth().background(Color.Black)) {
            val cameraWidth = minOf(maxWidth, maxHeight * CameraScanConfig.PREVIEW_ASPECT)
            Box(Modifier.width(cameraWidth).height(cameraWidth / CameraScanConfig.PREVIEW_ASPECT)
                .align(Alignment.Center).clipToBounds()) {
                AndroidView(factory = { previewView }, modifier = Modifier.fillMaxSize())
                A4GuideFrame(vm)
            }
        }
        if (camera?.cameraInfo?.hasFlashUnit() == true) FilterChip(selected = torch, onClick = { torch = !torch }, label = { Text(if (torch) "Tắt đèn" else "Bật đèn") })
    }
}

@Composable
fun A4GuideFrame(vm: ScannerViewModel) {
    val hits = vm.overlayHits
    val state = vm.overlayState
    androidx.compose.foundation.Canvas(modifier = Modifier.fillMaxSize()) {
        val w = size.width
        val h = size.height
        // PreviewView uses FIT_CENTER. Draw the target inside its visible area,
        // not the whole Compose box (the old A4 brackets spilled outside it).
        val aspect = vm.overlayAspect.takeIf { it > 0f } ?: (w / h)
        val contentW = minOf(w, h * aspect)
        val contentH = minOf(h, w / aspect)
        val offsetX = (w - contentW) / 2f
        val offsetY = (h - contentH) / 2f
        val guideW = minOf(contentW * CameraScanConfig.GUIDE_FILL,
            contentH * CameraScanConfig.GUIDE_FILL * CameraScanConfig.A4_ASPECT)
        val guideH = guideW / CameraScanConfig.A4_ASPECT
        val left = offsetX + (contentW - guideW) / 2f
        val top = offsetY + (contentH - guideH) / 2f
        val right = left + guideW
        val bottom = top + guideH
        val guide = androidx.compose.ui.graphics.Path().apply {
            moveTo(left, top)
            lineTo(right, top)
            lineTo(right, bottom)
            lineTo(left, bottom)
            close()
        }
        val guideColor = Color(0xFF00E676)
        drawPath(guide, guideColor.copy(alpha = if (state == "capturing") 1f else .8f),
            style = androidx.compose.ui.graphics.drawscope.Stroke(width = 3.dp.toPx()))
        listOf(
            androidx.compose.ui.geometry.Offset(left, top),
            androidx.compose.ui.geometry.Offset(right, top),
            androidx.compose.ui.geometry.Offset(right, bottom),
            androidx.compose.ui.geometry.Offset(left, bottom)
        ).forEach {
            drawCircle(guideColor, radius = 7.dp.toPx(), center = it,
                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2.dp.toPx()))
        }
        // A marker lights up as soon as it is seen. A detected paper outline
        // or four accepted markers starts the two-second stabilization wait.
        if (hits.size == 8) for (i in 0 until 4) {
            val x = hits[i * 2]
            val y = hits[i * 2 + 1]
            if (x != null && y != null) {
                drawCircle(guideColor, radius = 6.dp.toPx(),
                    center = androidx.compose.ui.geometry.Offset(
                        offsetX + x * contentW, offsetY + y * contentH))
            }
        }
    }
}


private fun displayDecision(data: JSONObject, field: String): String {
    val status = data.optString("status", "missing")
    val label = mapOf("ok" to "rõ", "blank" to "trống", "multiple" to "tô nhiều", "ambiguous" to "chưa rõ", "invalid" to "không hợp lệ", "missing" to "thiếu dữ liệu")[status] ?: status
    val value = if (data.isNull(field)) "—" else data.optString(field, "—").replace("Dung", "Đ").replace("Sai", "S")
    return "$value ($label)" + if (data.optString("source") == "manual") " • nhập tay" else ""
}

@Composable
fun ResultPanel(vm: ScannerViewModel, modifier: Modifier, onExport: () -> Unit) {
    val result = vm.result ?: return
    var showGrid by remember { mutableStateOf(false) }
    var showOriginal by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<Pair<String, String>?>(null) }
    val student = result.getJSONObject("student")
    LazyColumn(modifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Text("SBD: ${displayDecision(student.getJSONObject("so_bao_danh"), "value")}")
            Text("Mã đề: ${displayDecision(student.getJSONObject("ma_de"), "value")}")
            if (result.getJSONObject("quality").optString("overall_status") != "ok")
                Text("CẦN RÀ SOÁT • Mẫu hiện tại là mẫu thử nghiệm; đối chiếu phiếu trước khi dùng điểm.", color = MaterialTheme.colorScheme.error)
        }
        item { ContextFields(vm) { vm.grade() } }
        item {
            val grade = result.optJSONObject("grading")
            if (grade == null) Text("Chưa chấm điểm.")
            else if (grade.optString("status") == "unavailable") Text(grade.optString("message"))
            else {
                Text(if (grade.isNull("score")) "Điểm tạm: ${grade.optDouble("score_min")} – ${grade.optDouble("score_max")} / 10"
                    else "Điểm: ${grade.optDouble("score")} / 10", style = MaterialTheme.typography.titleLarge)
                val sections = grade.getJSONObject("sections")
                listOf("phan_1", "phan_2", "phan_3").forEachIndexed { index, name ->
                    val s = sections.getJSONObject(name)
                    Text("Phần ${index + 1}: ${s.getDouble("score_min")} – ${s.getDouble("score_max")} / ${s.getDouble("maximum")}")
                }
            }
        }
        item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = vm::reset, enabled = !vm.busy) { Text("Phiếu tiếp") }
            OutlinedButton(onClick = onExport, enabled = !vm.busy) { Text("Xuất JSON") }
        } }
        item { Row {
            TextButton(onClick = vm::grade, enabled = !vm.busy) { Text("Chấm lại") }
            TextButton(onClick = { showGrid = true }, enabled = !vm.busy) { Text("Xem ảnh chấm điểm") }
        } }
        item { Text("Ảnh: xanh = đúng, đỏ = sai, cam = chưa rõ, xám = chưa có đáp án.", style = MaterialTheme.typography.bodySmall) }
        item { TextButton(onClick = { showOriginal = true }) { Text("Xem khung hình gốc đã đọc") } }
        listOf("phan_1", "phan_2", "phan_3").forEachIndexed { index, section ->
            item { Text("Phần ${index + 1}", style = MaterialTheme.typography.titleLarge) }
            val part = result.getJSONObject(section)
            items(part.keys().asSequence().toList().sortedBy { it.toInt() }) { q ->
                val decision = part.getJSONObject(q)
                Text("Câu $q: " + if (section == "phan_2") listOf("a", "b", "c", "d").joinToString("   ") {
                    "$it: ${displayDecision(decision.getJSONObject(it), "answer")}"
                } else displayDecision(decision, if (section == "phan_3") "value" else "answer"))
                val editable = if (section == "phan_2") "abcd".any {
                    val d = decision.getJSONObject(it.toString())
                    d.optString("status") != "ok" || d.optString("source") == "manual"
                } else decision.optString("status") != "ok" || decision.optString("source") == "manual"
                if (editable) TextButton(onClick = { editing = section to q }, enabled = !vm.busy) {
                    Text("Nhập tay bài làm")
                }
                val details = result.optJSONObject("grading")?.optJSONArray("details")
                if (details != null) for (i in 0 until details.length()) {
                    val detail = details.getJSONObject(i)
                    if (detail.optString("section") == section && detail.optString("question") == q) {
                        val expected = if (section == "phan_2") {
                            val statements = detail.getJSONObject("statements")
                            listOf("a", "b", "c", "d").joinToString(" ") { "$it: ${statements.getJSONObject(it).getString("expected")}" }
                        } else detail.optString("expected")
                        Text("Đáp án: ${expected.replace("Dung", "Đ").replace("Sai", "S")} • Điểm ${detail.optDouble("score_min")} – ${detail.optDouble("score_max")}", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
    editing?.let { (section, q) -> AnswerCorrectionDialog(vm, section, q) { editing = null } }
    if (showGrid && vm.gridPath != null) GridPreview(result.optString("graded_image_path").ifBlank { vm.gridPath!! }, result.toString()) { showGrid = false }
    if (showOriginal && vm.gridPath != null) GridPreview(vm.gridPath!!.removeSuffix("_grid.png") + ".png") { showOriginal = false }
}

@Composable
fun GridPreview(path: String, revision: String = "", dismiss: () -> Unit) {
    val bitmap by produceState<android.graphics.Bitmap?>(null, path, revision) {
        value = withContext(Dispatchers.IO) { BitmapFactory.decodeFile(path) }
    }
    var scale by remember { mutableFloatStateOf(1f) }
    var x by remember { mutableFloatStateOf(0f) }; var y by remember { mutableFloatStateOf(0f) }
    Dialog(onDismissRequest = dismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding()) {
            Column {
                TextButton(onClick = dismiss) { Text("Đóng • Chụm hai ngón để phóng to, kéo để xem") }
                bitmap?.let { image ->
                    Image(image.asImageBitmap(), "Lưới các ô nhận diện trên phiếu", Modifier.fillMaxSize()
                        .pointerInput(Unit) { detectTransformGestures { _, pan, zoom, _ -> scale = (scale * zoom).coerceIn(1f, 6f); x += pan.x; y += pan.y } }
                        .graphicsLayer(scaleX = scale, scaleY = scale, translationX = x, translationY = y))
                }
            }
        }
    }
}

