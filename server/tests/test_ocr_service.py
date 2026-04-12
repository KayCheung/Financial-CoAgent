from app.services.ocr_service import ocr_service


def test_ocr_service_extracts_invoice_fields():
    text = "发票号码: INV-2026-001 金额: 88.50 元"

    fields = ocr_service._extract_invoice_fields(text)

    assert fields["invoice_number"] == "INV-2026-001"
    assert fields["amount"] == "88.50"
    assert fields["currency"] == "CNY"


def test_ocr_service_field_confidence():
    text = "发票号码: INV-2026-001 金额: 88.50 元"
    fields = ocr_service._extract_invoice_fields(text)
    conf = ocr_service._infer_field_confidence(fields, text)
    assert conf["invoice_number"] >= 0.8
    assert conf["amount"] >= 0.8
    assert "currency" in conf


def test_ocr_service_skips_invalid_attachment_with_reason():
    results = ocr_service.analyze_attachments(
        user_id="u1",
        attachments=[
            {"attachment_id": "a1", "file_name": "x.txt", "file_url": "/uploads/other-user/f.txt"},
        ],
    )
    assert len(results) == 1
    assert results[0].status == "skipped"
    assert results[0].failure_reason == "FILE_NOT_FOUND"
    assert results[0].doc_uri == "/uploads/other-user/f.txt"
