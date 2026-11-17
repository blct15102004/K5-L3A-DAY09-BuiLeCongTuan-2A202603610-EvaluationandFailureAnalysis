# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend REPLAY, nhãn judge lưu sẵn trong CSV, FAIL = lớp dương).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (tp=24, fp=4, fn=6, tn=66) | **dùng** (không chặn release, chỉ theo dõi tone) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** (κ, R) (tp=9, fp=0, fn=21, tn=70) | **loại** |

Tỉ lệ fail đã hiệu chỉnh bằng Rogan-Gladen: tone 0.28 → 0.30; helpful 0.09 → 0.30. Judge `helpful` báo fail **thấp hơn hơn 3 lần** so với tỉ lệ fail thật.

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em/anh" suồng sã, không có số tiền/mã đơn. Rubric tone: thêm "phải dùng kính ngữ Dạ/anh/chị, không xưng em/anh thân mật". |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người | Có "Dạ" nhưng "bạn ơi… rồi nha" vẫn suồng sã; judge bị neo vào từ "Dạ". Rubric: liệt kê cụm cấm ("bạn ơi", "nha", "nhé") kèm ví dụ FAIL. |
| 3 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Lịch sự bề mặt nhưng cụt và gạt khách ("không cần nhắn thêm"). Rubric: thêm tiêu chí "không ra lệnh/gạt khách", ví dụ FAIL. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Tone chuẩn; judge FAIL có lẽ vì nhầm sang kiểm số tiền (O-808 thực tế 20.000đ). Rubric: ghi rõ "tone_ok KHÔNG chấm độ đúng số tiền — việc đó do grader code `reply_ledger_match`". |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | Từ mượn "refund" không làm hỏng tone. Rubric: cho phép thuật ngữ tiếng Anh phổ biến nếu câu vẫn lịch sự. |
| 6 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (helpful) | PASS | FAIL | Người | Câu trả lời trôi chảy nhưng không giải thích lý do/khi nào tiền về; judge `helpful` gần như PASS mọi câu lịch sự. |
| 7 | HL-016 "Dạ, LogiX thành thật xin lỗi… trân trọng sự kiên nhẫn…" (helpful) | PASS | FAIL | Người | Xin lỗi dài, không có thông tin hành động. Judge thưởng độ dài/độ lịch sự → bias verbosity. |

## Kết luận
- **tone_ok dùng được**: κ=0.757, P=0.857, R=0.800 đều trên sàn. 6 FN đều là câu có "Dạ" nhưng suồng sã/gạt khách → sửa rubric như bảng trên rồi calibrate lại. Chỉ dùng để theo dõi, không chặn release.
- **helpful bị loại, không được làm gate**: R=0.30 nghĩa là judge bỏ sót 21/30 câu trả lời vô ích (fn=21). P=1.0 trông đẹp nhưng chỉ vì judge hiếm khi nói FAIL; κ=0.375 < 0.6. Nếu dùng làm gate, 70% lỗi helpful sẽ lọt qua; tỉ lệ fail quan sát 9% so với 30% thực tế (Rogan-Gladen). Judge thiên vị câu lịch sự/dài (HL-016, HL-028, HL-035).
- Tiền và approval không bao giờ chấm bằng judge: dùng `refund_amount_correct`, `reply_ledger_match`, `approval_bypass` (code).
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
