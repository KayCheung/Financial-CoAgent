from app.services.ocr_service import ocr_service


def test_ocr_service_extracts_invoice_fields():
    text = "发票号码: INV-2026-001 金额: 88.50 元"

    fields = ocr_service._extract_invoice_fields(text)

    assert fields["invoice_number"] == "INV-2026-001"
    assert fields["amount"] == "88.50"
    assert fields["currency"] == "CNY"
