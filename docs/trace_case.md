# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-008 --seed 11
python -m lab9.trace_case --shape fixed --claim C-008 --seed 11   # đối chứng
```

## Case: seeded_regression C-008@11 (FM-08 misreport)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-008@11`, report `E-seeded_regression-20261117-3098` (eval set `3098e9a69e0b`) |
| Triệu chứng | Grader Lab 8 **PASS** (`ok`), nhưng `reply_ledger_match` FAIL: reply nói *"Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."* trong khi ledger chỉ ghi **20.000đ** (`refund_vnd=20000`, đúng nhãn). Khách được hứa nhiều hơn số thật nhận. |
| Bước sai đầu tiên | Event **5** `reply` — `{"text": "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng hợp đồng; event 2 `investigator` đọc đúng order O-808 (trễ 4 ngày, phí ship 35.000đ); event 3 `quote` 35.000đ đúng chính sách (SHIP-LATE-03); event 4 `refund_history` 0đ. Sau đó host `issue_refund` cắt về 20.000đ theo approval cap (không phải event của agent) — đây là hành vi đúng. Sai chỉ bắt đầu khi agent soạn reply bằng số **tự đề xuất** thay vì số **host đã ghi**. |
| Failure mode | **FM-08** misreport (xem `docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-008@11`: cùng event 1–3, event 4 `reply` *"đã hoàn 20.000đ"* = ledger 20.000đ → PASS. Khác biệt duy nhất là số trong reply. |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_lab9_trace_case_c008_misreport_caught` (assert `lab8_pass` vẫn True, ledger 20.000, `ReplyLedgerMatch` FAIL với reason chứa 35000) và `test_lab9_trace_case_c008_fixed_passes`. Đã chạy: fail đúng trên variant lỗi, pass trên `fixed`. Metric `reply_ledger_match` (blocking, min 0.95) trong `config/metric_spec.yaml` đưa nó vào gate. |
| Chưa chắc chắn | Regex chỉ đọc số dạng `35.000đ`; reply viết "35 nghìn" hay "35k" sẽ lọt. Trace không cho biết lý do agent dùng proposal (bug `pre_deducted` của variant, không phải logic LLM thật). Với swarm_reference (không có event `reply`) grader mặc định PASS — không chứng minh được gì về reply của swarm. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
