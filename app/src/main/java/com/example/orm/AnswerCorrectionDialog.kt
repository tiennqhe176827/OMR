package com.example.orm

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.json.JSONObject

@Composable
fun AnswerCorrectionDialog(vm: ScannerViewModel, section: String, q: String, dismiss: () -> Unit) {
    val answer = vm.result!!.getJSONObject(section).getJSONObject(q)
    fun editable(d: JSONObject) = d.optString("status") != "ok" || d.optString("source") == "manual"
    val fields = if (section == "phan_2") "abcd".map { it.toString() }.filter { editable(answer.getJSONObject(it)) }
        else listOf("value")
    var values by remember(section, q) { mutableStateOf(fields.associateWith { field ->
        val d = if (section == "phan_2") answer.getJSONObject(field) else answer
        if (d.optString("source") == "manual") d.optString(if (section == "phan_3") "value" else "answer") else ""
    }) }
    AlertDialog(onDismissRequest = { if (!vm.busy) dismiss() },
        title = { Text("Nhập bài làm • Câu $q") },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Đối chiếu ảnh rồi nhập câu trả lời học sinh đã tô trên phiếu.")
            fields.forEach { field ->
                if (section == "phan_3") OutlinedTextField(values[field] ?: "",
                    { values = values + (field to it) }, label = { Text("Giá trị, ví dụ -1,5") }, singleLine = true, enabled = !vm.busy)
                else {
                    if (section == "phan_2") Text("Ý $field")
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        val options = if (section == "phan_1") listOf("A", "B", "C", "D") else listOf("Dung", "Sai")
                        options.forEach { value -> FilterChip(selected = values[field] == value,
                            onClick = { values = values + (field to value) }, enabled = !vm.busy,
                            label = { Text(when (value) { "Dung" -> "Đúng"; "Sai" -> "Sai"; else -> value }) }) }
                    }
                }
            }
            Text(vm.message, style = MaterialTheme.typography.bodySmall)
        } },
        confirmButton = { TextButton(enabled = !vm.busy && fields.all { !values[it].isNullOrBlank() },
            onClick = { vm.correctAnswer(section, q, JSONObject().apply { values.forEach { (k, v) -> put(k, v) } }, dismiss) }) {
            Text("Lưu và chấm lại")
        } },
        dismissButton = { TextButton(onClick = dismiss, enabled = !vm.busy) { Text("Hủy") } })
}
