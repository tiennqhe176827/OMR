# OMR Android — Jetpack Compose + CameraX

## Bản 1.17 — thêm mẫu THPT CV 1239 mã đề 4 số

Chọn **THPT CV 1239 • mã đề 4 số** trong màn hình Quét phiếu trước khi chụp. App nhớ mẫu đã chọn; đổi mẫu hủy lượt nhận diện và đếm ngược cũ. Mẫu cũ vẫn có trong danh sách. Mẫu mới đo từ trang đầu PDF trắng: 8 cột SBD, 4 cột mã đề, 40 câu Phần I, 8 câu x 4 ý Phần II, 6 câu x 4 cột Phần III; 602 ô và 6 marker phụ. Trang sau là hướng dẫn, không dùng để quét.

Có ảnh tham chiếu trắng kèm checksum; template vẫn experimental cho đến khi kiểm chứng trên phiếu in/camera thực. Kiểm thử phiếu trắng không sinh lựa chọn giả; tô giả lập gồm mã đề 0123 giữ số 0 đầu, số âm, dấu phẩy, cột cuối trống; kiểm tra phối cảnh và giảm độ phân giải. Giữ SDK 31, ARM 32/64-bit, nhập tay và màu chấm điểm. APK: `dist/OMR-camera-1.17-sdk31-arm32-debug.apk`.

## Bản 1.16 — hỗ trợ ARM 32-bit

Bổ sung ABI `armeabi-v7a` cùng `arm64-v8a` và `x86_64` để hỗ trợ hệ điều hành ARM 32-bit. Giữ minSdk 31; Python 3.10, NumPy/OpenCV có wheel ARM 32-bit. APK: `dist/OMR-camera-1.17-sdk31-arm32-debug.apk`. Chưa xác minh trực tiếp Android/ABI của Galaxy A13 người dùng; máy ADB hiện tại là realme RMX3760.

## Bản 1.15 — hỗ trợ Android 12 / API 31

Hạ `minSdk` từ 34 xuống 31 để APK cho phép cài trên Android 12 trở lên. Giữ compileSdk/targetSdk 37 cho các thư viện hiện tại. Giữ nhập tay, ảnh chấm điểm và đợi chụp 2 giây. APK: `dist/OMR-camera-1.17-sdk31-arm32-debug.apk`. Cần kiểm tra thực tế trên Galaxy A13 chạy Android 12.

## Bản 1.14 — nhập tay bài làm và ảnh chấm điểm

Ở câu chưa rõ/trống/tô nhiều, bấm **Nhập tay bài làm**, nhập A/B/C/D, Đúng/Sai từng ý chưa rõ hoặc giá trị số Phần III rồi **Lưu và chấm lại**. Lưu kết quả nhận diện ban đầu trong `original_recognition`; bài làm nhập tay được gắn `source=manual`, không sửa bộ đáp án đúng. Có thể chỉnh lại phần đã nhập tay. Kết quả sửa được lưu cùng phiếu, dùng khi mở lịch sử và xuất JSON.

**Xem ảnh chấm điểm** hiện xanh cho đúng, đỏ cho sai theo bộ đáp án, cam cho chưa rõ, xám khi không có đáp án/câu ngoài phạm vi môn. Phần III có khung màu cho từng câu; sửa tay có nhãn MANUAL. Ảnh gốc vẫn xem riêng. Đổi bài/môn, sửa tay hoặc Chấm lại đều tạo lại ảnh màu. APK: `dist/OMR-camera-1.14-debug.apk`.

## Bản 1.13 — tránh nhận viền in thành nét tô yếu

Tái hiện Phần III câu 2 có giá trị 0 nhưng báo chưa rõ vì ba cột trống bị viền in tạo điểm 0,14–0,19. Lấy mẫu trong nửa bán kính ô thay cho 0,65 để tránh viền dày/lệch nhẹ; giữ các ngưỡng phân loại. Ảnh báo lỗi đọc đúng 2108, 0, 0,31, 1, 4, 9; các ô đã rõ trong ảnh giữ nguyên. Hai ảnh quét khác cũng giữ các lựa chọn đã rõ. Có kiểm thử viền lệch, tô chì nhạt, bóng và tô nhiều ô. Giữ thời gian đợi 2 giây. APK: `dist/OMR-camera-1.13-debug.apk`.

## Bản 1.12 — sửa căn chỉnh cục bộ trên ảnh camera

Tái hiện lỗi Phần II 3,80/3,65 px trên ảnh chẩn đoán. Cho phép thử căn chỉnh bằng lưới marker khi lưới ô lệch dù marker vẫn dưới ngưỡng 7 px. Ảnh sửa phải qua toàn bộ kiểm tra marker và neo in độc lập, giữ ngưỡng cục bộ 3,5 px. Giữ thời gian đợi 2 giây. APK: `dist/OMR-camera-1.12-debug.apk`.

## Bản 1.11 — đợi giấy ổn định 2 giây

Giảm thời gian tự chụp từ 3 xuống 2 giây. Giữ cơ chế đếm lại khi giấy di chuyển hoặc mất nhận diện. APK: `dist/OMR-camera-1.11-debug.apk`.

## Bản 1.10 — đợi giấy ổn định 3 giây trước khi tự chụp

Sau khi nhận diện giấy đủ điều kiện, app hiện đếm ngược 3 giây rồi giữ khung camera mới nhất. Mất nhận diện, dịch chuyển góc quá 2,5% khung, gián đoạn khung quá 1,5 giây, rời màn hình hoặc Quét lại sẽ hủy thời gian đã đợi. Nút **Chụp ngay** vẫn chụp chủ động. Ảnh đã giữ tiếp tục qua toàn bộ kiểm tra OMR.

APK: `dist/OMR-camera-1.10-debug.apk`.

## Bản 1.8 — nhận ra phiếu là chụp, xử lý trên ảnh tĩnh

Camera tự chụp ở khung hình **đầu tiên** nhận được bốn marker có hình học hợp lệ **hoặc** viền phiếu đầy đủ, đủ lớn và có nét in. Không chờ rung tay dừng, không chờ đủ nhiều khung, không ép bốn marker khớp khung hướng dẫn, và không chặn chụp vì ngưỡng kích thước marker. Khung xanh vẫn giúp đưa trọn phiếu vào ảnh, nhưng không phải điều kiện khóa cửa trập. Sau khi lưu JPEG, pipeline OMR trên ảnh độ phân giải cao mới tìm marker, căn phối cảnh/trải phẳng, kiểm tra chất lượng, đọc ô tô và chấm theo đáp án. Ảnh quá mờ, thiếu marker trên ảnh tĩnh hoặc không khớp mẫu vẫn bị từ chối rõ ràng, không sinh điểm sai.

Viền giấy được phát hiện bằng tứ giác sáng bao trọn trong camera, chiếm ít nhất 20% khung và có nét in; khung trắng, giấy bị cắt mép không tự chụp. Chế độ này giúp camera chụp được khi chưa xác định đủ bốn marker từ preview; bốn marker vẫn là đường kích hoạt nhanh thứ hai.

## Bản 1.7 — chụp ngay khi khung hợp lệ

Tracker vẫn xác nhận bốn marker ở khung hình hợp lệ đầu tiên, không đợi thêm nhiều khung. Ngưỡng chuyển động góc khi cầm tay tăng từ 1,2% lên 2,5% đường chéo khung phân tích; vẫn từ chối ảnh mờ, phiếu quá nhỏ hoặc lệch khung. Thông báo nêu rõ lý do nếu đã thấy bốn góc nhưng chưa thể chụp. ImageCapture dùng chế độ ưu tiên độ trễ thấp. Ngay sau khi lưu ảnh, giao diện đổi từ **“đang chụp ảnh”** sang **“Ảnh đã chụp — đang đọc đáp án”** và hiện thanh tiến trình trong lúc OMR xử lý.

## Bản 1.6 — yêu cầu phiếu đủ lớn trong camera

Khung xanh được tăng để bốn marker góc phải chiếm phần lớn vùng xem. Tracker đo cả phần diện tích phiếu trong khung phân tích và kích thước marker sau khi quy đổi về ảnh rộng 960 px. Nếu diện tích dưới 34% hoặc marker góc nhỏ hơn 13 px ở kích thước quy đổi, app báo **“Phiếu còn nhỏ — đưa máy lại gần”**, không tự chụp và cũng chặn nút Đọc phiếu khi đã xác định phiếu quá nhỏ. Cách này tránh trường hợp thấy đủ bốn dấu nhưng ô tô trên ảnh tĩnh lại quá ít pixel để chấm chắc chắn.

Ảnh tĩnh gần nhất trên điện thoại trong phản hồi ngày 1/10 có phần diện tích phiếu 30,3% và marker góc tương đương 11,4 px ở bề rộng 960 px. Bản 1.6 nhận ra bốn góc nhưng chủ động từ chối chụp với thông báo đưa máy lại gần; đây là đúng trường hợp người dùng vừa báo.

## Bản 1.5 — khung căn giấy luôn hiện và phản hồi từng góc

- Khung xanh nằm **bên trong vùng camera ngay khi mở tab Quét phiếu**. Đưa bốn ô vuông góc giấy gần bốn góc khung; mỗi marker gần góc được đánh dấu ngay trong khung hình. Khi đủ bốn góc, hình học và độ nét hợp lệ, app chụp ngay thay vì chờ ba khung liên tiếp. Chấm điểm vẫn chỉ chạy sau khi ảnh tĩnh qua toàn bộ xác minh OMR.
- Preview, ImageAnalysis và ImageCapture cùng dùng CameraX ViewPort; mặt phẳng Y được cắt theo `ImageProxy.cropRect` trước khi đưa vào tracker. Điều này sửa lỗi khung động bị phóng lệch so với phiếu do Preview và Analysis có vùng nhìn khác nhau.
- Nếu OMR từ chối ảnh, app giữ nguyên lý do lỗi và dừng để người dùng căn lại rồi bấm **Quét lại**, thay vì chụp lặp gây hỗn loạn. Lỗi cũ biến mất ngay khi bắt đầu lần chụp mới.
- Ảnh gốc lấy từ lần chụp trên RMX3760 trong phản hồi ngày 1/10 xử lý thành công bằng chính pipeline Android khi chạy lại. Dòng `alignment_failed` đang hiển thị cùng chữ “đang chụp ảnh” trong ảnh màn hình là lỗi của lần chụp trước chưa được xóa khỏi giao diện. Ảnh gốc vẫn cần được xem như dữ liệu riêng của người dùng, không đưa vào repository.

## Bản 1.4 — theo dõi marker theo báo cáo kiến trúc mobile

Giữ nguyên mẫu giấy với bốn ô vuông góc hiện tại. CameraX phân tích mặt phẳng Y ở chế độ chỉ giữ khung mới nhất. Tracker giảm ảnh xuống tối đa 960 px, phát hiện marker, theo dõi 16 điểm trên viền bốn marker bằng Lucas–Kanade với kiểm tra xuôi–ngược, phát hiện lại định kỳ mỗi 5 khung, tìm lại trong vùng gần vị trí cũ và giữ góc hợp lệ 5 khung khi mất dấu. Hình học, độ dịch chuyển từng góc, biến động sáng và độ nét được kiểm tra trước khi chụp tự động. Khung bị mờ hoặc mất góc không kích hoạt chụp. Overlay Compose vẽ theo đúng tỉ lệ của khung phân tích.

CameraX ImageCapture lấy ảnh tĩnh độ phân giải cao sau khi khóa; toàn bộ pipeline OMR gốc vẫn kiểm tra mẫu, căn chỉnh lưới, đọc SBD/mã đề/đáp án rồi mới cho chấm bằng bộ đáp án được lưu trong app. Nút **Đọc phiếu** cho phép thử chụp thủ công nhưng không bỏ qua kiểm tra OMR. Khi OMR thất bại, thông báo mã lỗi và tiếp tục quét tự động. Gói chẩn đoán có thêm thời gian phát hiện/theo dõi, độ nét, độ sáng và trạng thái mất dấu.

Báo cáo đề xuất ArUco/AprilTag có ID là hướng tốt hơn nếu được in lại phiếu. Mẫu hiện tại là ô vuông trơn nên không có ID để phân biệt marker; thuật toán 1.4 cải thiện việc bám theo nhưng không thể đảm bảo đúng trong mọi trường hợp bị che/lóa. Template hiện đóng gói còn trạng thái experimental, nên điểm có thể là khoảng điểm tạm và cần đối chiếu trước khi sử dụng chính thức.

## Bản 1.2 — sửa bước giữ ổn định sau khi xem video n.mp4

Video người dùng gửi dài khoảng 46,6 giây cho thấy chủ yếu trạng thái đủ 4 marker, 1/3 hoặc 2/3 rồi trở lại 1/3. Có các thời điểm báo mờ và gần mép; không thấy lỗi khớp mẫu trong các khung đã kiểm tra. Video là bản quay màn hình đã giảm độ phân giải, không thay thế khung ImageAnalysis gốc để kết luận độ chính xác đọc ô.

- Điều kiện chụp tự động chấp nhận dịch chuyển góc tối đa 2,5% khung thay cho 1,2%, và khoảng giữa các lượt phân tích tới 8 giây thay cho 3 giây để hỗ trợ máy xử lý chậm. Không đổi ngưỡng độ mờ, orientation hay alignment của pipeline.
- Nút **Đọc phiếu** đọc khung camera mới khi người dùng yêu cầu, không cần đợi đủ ba khung. Vẫn phải qua kiểm tra chất lượng, đủ bốn góc, bố cục và căn chỉnh. Nếu thất bại thì giữ thông báo để đọc rõ, bấm Đọc phiếu/Quét lại để thử tiếp.
- 9 test adapter gồm rung nhẹ, xử lý chậm, di chuyển lớn, đọc chủ động và từ chối khung trắng. Cần thử APK 1.2 trên điện thoại; chưa đo thời gian xử lý trên thiết bị của người dùng.

## Bản 1.1 — sửa bắt marker trên camera

- Tái hiện lỗi trên nền tối: chế độ lấy contour ngoài cùng bỏ qua toàn bộ marker nằm trong vùng giấy. Đã duyệt contour lồng nhau trong vùng lớn, loại contour lỗ và thành phần bên trong vòng tròn nhỏ.
- Thêm kiểm tra diện tích tứ giác so với contour để vòng tròn đáp án đã tô không bị nhận thành marker vuông. Không nới ngưỡng alignment hoặc bỏ kiểm tra khớp mẫu.
- Bỏ lặp việc chọn góc với cùng cụm kích thước marker; sao chép mặt phẳng Y theo hàng để giảm overhead camera.
- Phân biệt lỗi tìm marker, xác định bố cục và căn chỉnh lưới. Hiện mã lỗi cụ thể; nút **Xuất chẩn đoán** tạo ZIP chứa khung camera vừa phân tích, overlay marker và JSON lỗi/thông số/mẫu. File chỉ lưu tới nơi người dùng chọn, không tự gửi ra ngoài. Gói có chứa nội dung phiếu; chỉ chia sẻ khi cần hỗ trợ.
- Kiểm chứng bản 1.1: 57 test desktop (55 đạt, 2 thiếu ảnh được bỏ qua); 24/24 biến thể synthetic giữ 105/105 group; 12/12 cảnh mô phỏng từ ảnh phiếu thật giữ đáp án của bản gốc. Các kiểm thử này không thay thế thử camera trên điện thoại.
- 7/7 test camera adapter đạt, gồm quét phiếu trên nền tối và xuất đúng lỗi căn chỉnh vào gói chẩn đoán. APK build và Gradle unit test/lint đã qua.
- `tools/check_camera_scenes.py` và `camera-scenes-report.json` lưu kiểm tra nền tối, bóng đổ, phối cảnh, độ phân giải và dải Y camera trên mẫu thật. Không dùng kết quả tự sinh làm ground truth độc lập.

Ứng dụng đọc trực tiếp camera sau, chạy OMR trên điện thoại, không cần server hay tải ảnh lên mạng. Giao diện dùng Jetpack Compose/Material 3; CameraX PreviewView được nhúng bằng AndroidView.

## Sử dụng

1. Cài `dist/OMR-camera-1.17-sdk31-arm32-debug.apk` trên Android 12+ (ARM 32-bit hoặc 64-bit). Đây là APK debug dùng thử.
2. Tab **Đáp án**: nhập bài kiểm tra, môn, mã đề (giữ số 0 đầu); tạo đáp án bằng các ô chọn A/B/C/D, Đúng/Sai và ô nhập số. Tin học chọn đúng 4 trong 6 câu. Có thể nhập một file JSON đáp án từ ứng dụng máy tính. Dữ liệu chỉ được lưu sau khi bấm **Lưu** và qua validation.
3. Tab **Quét phiếu**: cấp quyền camera, đưa trọn phiếu vào khung xanh có sẵn, chạm lấy nét nếu cần; bật đèn khi thiếu sáng. Khi thấy viền giấy hoặc đủ bốn marker, app đếm ngược 2 giây giữ ổn định rồi chụp khung mới nhất và xử lý ảnh. Nút **Đọc phiếu** cho phép chụp chủ động; ảnh vẫn phải qua toàn bộ bước kiểm tra OMR.
4. Xem SBD, mã đề, ba phần đáp án, trạng thái từng câu, điểm từng câu/phần và điểm tổng. Có thể phóng to lưới hoặc khung hình gốc. Đổi bài/môn sẽ chấm lại theo đúng ngữ cảnh. **Phiếu tiếp** bắt đầu lượt mới để tránh đọc trùng.
5. Kết quả, khung gốc và lưới nằm trong vùng lưu trữ riêng của app, có thể mở lại ở **Lịch sử**. **Xuất JSON** dùng bộ chọn nơi lưu của Android. Gỡ app sẽ xóa dữ liệu nội bộ; xuất đáp án/kết quả cần giữ trước đó.

## Cấu trúc

- `app/src/main/java/com/example/orm/ScannerScreen.kt`: Compose, quyền camera, Preview, kết quả và lịch sử.
- `KeyEditor.kt`: nhập/sửa đáp án bằng Compose.
- `ScannerViewModel.kt`: trạng thái, một executor nền, lifecycle và kết nối Python.
- `app/src/main/python/camera_tracker.py`: phát hiện, KLT, tìm lại, kiểm tra hình học/độ nét và điều kiện chụp.
- `app/src/main/python/android_bridge.py`: nhận byte của mặt phẳng Y, xử lý xoay, gọi pipeline trên ảnh tĩnh, lưu và chấm điểm.
- `app/src/main/python/omr/` + `config.py`: bản sao nguyên module lõi từ `../cdtd/omr_system`. Bao gồm alignment, local warp, grid registration, scoring, decoder và grading. Giao diện Tk không được gọi trên Android.
- `app/src/main/python/templates/`: đúng template/reference hiện có; giữ nguyên checksum và trạng thái experimental.
- `tools/sync_core.py`: đồng bộ lõi/template khi bản máy tính được sửa. Không sao chép bài thi, đáp án riêng hoặc output người dùng.

Thay đổi chung duy nhất ở pipeline: `process_exam_sheet` nhận được cả đường dẫn cũ và mảng BGR trong bộ nhớ. Luồng phân tích camera chỉ tìm marker; ảnh JPEG từ ImageCapture được đọc một lần cho OMR.

## Build

Mở thư mục này bằng Android Studio, Sync Gradle rồi Run. Giữ JDK/SDK đang dùng của project (compileSdk/targetSdk 37, minSdk 31). Build cần Python 3.10: Chaquopy tự tìm `py -3.10` hoặc `python`; môi trường workspace hiện tại dùng bản riêng tại `.tools/python310/tools/python.exe` (không commit). OpenCV Android được đóng gói qua Chaquopy 17.0.0, `opencv-python-headless==4.5.1.48`, NumPy 1.26.2; armeabi-v7a, arm64-v8a và x86_64.

```powershell
./gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
./.tools/python310/tools/python.exe -m unittest discover -s tests -v
# Khi đã kết nối điện thoại/máy ảo:
./gradlew.bat :app:assembleDebugAndroidTest
# Cài hai APK bằng adb install -r rồi chạy am instrument để giữ dữ liệu app đang có.
```

Chaquopy chưa hỗ trợ configuration cache trong cấu hình này, nên đã tắt. Project giữ AGP 9.4.1 sẵn có: build thực tế đã qua, dù ma trận tài liệu Chaquopy hiện chỉ liệt kê kiểm thử tới AGP 9.2.

## Kiểm chứng và giới hạn

- Đã build APK Compose, chạy unit test Gradle và lint (0 lỗi; vẫn có cảnh báo dependency/style).
- 12 kiểm thử adapter Python 3.10 đạt: byte/xoay, phản hồi từ marker đầu tiên, chụp phiếu nhỏ khi đã nhận marker, chụp khi thấy viền giấy trước khi đủ marker, từ chối nền trắng/giấy cắt mép, rung tay nhẹ, khóa 4 marker, giữ vị trí khi mờ/mất góc và tìm lại, đọc JPEG độ phân giải cao đúng 105 nhóm ô trên mẫu tổng hợp, lỗi OMR và revision/chấm đáp án.
- 41 kiểm thử lõi OMR không phụ thuộc Tk đã chạy: 39 đạt, 2 bỏ qua do thiếu ảnh người dùng; 2 module kiểm thử giao diện Tk không chạy trong Python 3.10 đóng gói vì môi trường đó không có tkinter.
- Replay 187 khung lấy cách nhau khoảng 0,25 giây từ video n.mp4: 144 khung ở trạng thái locked, lần khóa đầu tại 0,5 giây, thời gian xử lý tracker trung vị 10,3 ms và p95 67,9 ms trên máy tính. Video là bản quay màn hình, không phải Y plane gốc; số liệu này chỉ chứng minh logic theo dõi trên chính video lỗi đã gửi.
- Bộ máy tính: 53 test, 51 đạt và 2 bỏ qua vì thiếu các ảnh hồi quy ngoài workspace.
- Ba Android instrumented test tải thư viện native/template, kiểm tra Java byte[] sang Python, khung không marker và viền giấy kích hoạt chụp ở khung đầu tiên đã chạy trên RMX3760 (Android 15). Chưa đo FPS, RAM hoặc tỉ lệ nhận diện trên camera với phiếu thật; video n.mp4 là quay màn hình nên không thay thế được dữ liệu Y gốc từ CameraX.
- Mẫu hiện tại là **experimental**, nên điểm vẫn là điểm tạm và yêu cầu đối chiếu. Camera giúp thử nhiều khung hình nhưng không đảm bảo nhận được marker bị che, giấy cong hoặc mẫu phiếu sai.
- Công cụ hiệu chuẩn bằng chuột/Tk của bản máy tính chưa có giao diện Android. Hiện dùng template đã đóng gói; hiệu chuẩn mẫu mới ở máy tính rồi chạy `tools/sync_core.py` và build lại.

Tài liệu tham chiếu: [CameraX ImageAnalysis](https://developer.android.com/media/camera/camerax/analyze), [Chaquopy Gradle](https://chaquo.com/chaquopy/doc/current/android.html).
