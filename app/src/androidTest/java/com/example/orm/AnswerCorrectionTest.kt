package com.example.orm

import android.app.Application
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.core.app.ApplicationProvider
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class AnswerCorrectionTest {
    @get:Rule val compose = createComposeRule()

    @Test fun unclearShortAnswerCanBeEnteredAndRegraded() {
        val app = ApplicationProvider.getApplicationContext<Application>()
        val vm = ScannerViewModel(app)
        compose.setContent { ScannerApp(vm) }
        compose.waitUntil(15000) { vm.ready }
        val data = JSONObject("""{
            "status":"ok", "quality":{"overall_status":"ok"},
            "student":{"so_bao_danh":{"status":"blank","value":null},"ma_de":{"status":"ok","value":"999999"}},
            "phan_1":{},"phan_2":{},"phan_3":{"2":{"status":"ambiguous","value":null}},"groups":{}
        }""")
        val file = app.cacheDir.resolve("manual-ui-test.json").apply { writeText(data.toString()) }
        compose.runOnIdle { vm.openScan(file) }
        compose.waitUntil(15000) { vm.result != null && !vm.busy }
        compose.onNodeWithText("Nhập tay bài làm").performScrollTo()
        compose.waitForIdle()
        compose.onNodeWithText("Nhập tay bài làm").assertIsEnabled().performClick()
        compose.waitUntil(10000) { compose.onAllNodesWithText("Giá trị, ví dụ -1,5").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("Giá trị, ví dụ -1,5").performTextInput("-1,5")
        compose.onNodeWithText("Lưu và chấm lại").performClick()
        compose.waitUntil(15000) { vm.result?.getJSONObject("phan_3")?.getJSONObject("2")?.optString("source") == "manual" && !vm.busy }
        compose.runOnIdle {
            val answer = vm.result!!.getJSONObject("phan_3").getJSONObject("2")
            assertEquals("-1,5", answer.getString("value"))
            assertEquals("ambiguous", answer.getJSONObject("original_recognition").getString("status"))
            vm.pause()

            file.delete()
        }
    }
}
