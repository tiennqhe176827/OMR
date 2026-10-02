package com.example.orm

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import org.json.JSONArray
import org.json.JSONObject

@Composable
fun KeyEditor(vm: ScannerViewModel, onExport: () -> Unit) {
    val data = JSONObject(vm.keyText!!)
    fun update(section: String, q: String, value: Any) {
        data.getJSONObject(section).put(q, value); vm.keyText = data.toString()
    }
    Dialog(onDismissRequest = { if (!vm.busy) vm.keyText = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding()) {
            Column(Modifier.padding(16.dp)) {
                Text("Đáp án ${data.getString("subject")} • mã ${data.getString("code")}", style = MaterialTheme.typography.titleLarge)
                Text(data.getString("exam"))
                Text(vm.message, color = MaterialTheme.colorScheme.primary)
                Row {
                    Button(onClick = vm::saveKey, enabled = !vm.busy) { Text("Lưu") }
                    TextButton(onClick = onExport, enabled = !vm.busy) { Text("Xuất") }
                    TextButton(onClick = { vm.keyText = null }, enabled = !vm.busy) { Text("Đóng") }
                }
                LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (data.getString("subject") == "Tin học") item {
                        Text("Chọn đúng 4 câu Phần II theo đề và định hướng:")
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            (1..6).forEach { q ->
                                val part = data.getJSONObject("phan_2")
                                FilterChip(selected = part.has(q.toString()), enabled = !vm.busy, onClick = {
                                    if (part.has(q.toString())) part.remove(q.toString())
                                    else part.put(q.toString(), JSONObject().apply { "abcd".forEach { put(it.toString(), "") } })
                                    data.put("tf_questions", JSONArray(part.keys().asSequence().map { it.toInt() }.sorted().toList()))
                                    vm.keyText = data.toString()
                                }, label = { Text("$q") })
                            }
                        }
                    }
                    listOf("phan_1", "phan_2", "phan_3").forEachIndexed { index, section ->
                        val part = data.getJSONObject(section)
                        if (part.length() > 0) item { Text("Phần ${index + 1}", style = MaterialTheme.typography.titleMedium) }
                        items(part.keys().asSequence().toList().sortedBy { it.toInt() }, key = { "$section:$it" }) { q ->
                            if (section == "phan_1") {
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text("$q", Modifier.padding(top = 16.dp))
                                    listOf("A", "B", "C", "D").forEach { answer ->
                                        FilterChip(selected = part.optString(q) == answer, onClick = { update(section, q, answer) }, enabled = !vm.busy, label = { Text(answer) })
                                    }
                                }
                            } else if (section == "phan_2") {
                                Text("Câu $q")
                                "abcd".forEach { item ->
                                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Text("$item", Modifier.padding(top = 16.dp))
                                        listOf("Dung", "Sai").forEach { answer ->
                                            FilterChip(selected = part.getJSONObject(q).optString(item.toString()) == answer,
                                                onClick = { update(section, q, part.getJSONObject(q).put(item.toString(), answer)) },
                                                enabled = !vm.busy, label = { Text(if (answer == "Dung") "Đúng" else "Sai") })
                                        }
                                    }
                                }
                            } else OutlinedTextField(part.getString(q), { update(section, q, it) }, label = { Text("Câu $q") }, singleLine = true, enabled = !vm.busy)
                        }
                    }
                }
            }
        }
    }
}
