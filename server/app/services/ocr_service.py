from __future__ import annotations

import json
import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib import request

from app.core.config import get_settings


@dataclass(slots=True)
class OcrAttachmentResult:
    """单附件 OCR 结果，字段对齐 T1.6 工具契约：doc_uri、fields、confidence。"""

    attachment_id: str
    file_name: str
    doc_uri: str
    provider: str
    extracted_text: str
    summary: str
    parsed_fields: dict[str, str]
    confidence: dict[str, float]
    status: str
    failure_reason: str | None = None


class OcrService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def analyze_attachments(self, *, user_id: str, attachments: list[dict]) -> list[OcrAttachmentResult]:
        results: list[OcrAttachmentResult] = []
        for attachment in attachments:
            doc_uri = str(attachment.get("file_url") or "").strip()
            file_name = str(attachment.get("file_name") or "")
            attachment_id = str(attachment.get("attachment_id") or "")
            file_path = self._resolve_local_path(user_id=user_id, attachment=attachment)
            if not file_path or not file_path.exists():
                reason = "RESOLVE_PATH_FAILED" if not doc_uri.startswith("/uploads/") else "FILE_NOT_FOUND"
                results.append(
                    OcrAttachmentResult(
                        attachment_id=attachment_id or "unknown",
                        file_name=file_name or "unknown",
                        doc_uri=doc_uri,
                        provider="none",
                        extracted_text="",
                        summary="附件路径无效或文件不存在，已跳过 OCR",
                        parsed_fields={},
                        confidence={},
                        status="skipped",
                        failure_reason=reason,
                    )
                )
                continue
            results.append(self._analyze_file(file_path=file_path, attachment=attachment))
        return results

    def _analyze_file(self, *, file_path: Path, attachment: dict) -> OcrAttachmentResult:
        doc_uri = str(attachment.get("file_url") or "").strip()
        remote_text = self._try_remote_ocr(file_path)
        if remote_text:
            text = remote_text.strip()
            provider = "remote_ocr"
        else:
            text = self._extract_local_text(file_path)
            provider = "local_fallback"

        is_placeholder = text.startswith("Attachment ready for OCR:")
        parsed_fields = self._extract_invoice_fields(text)
        confidence = self._infer_field_confidence(parsed_fields, text)

        if is_placeholder and not parsed_fields:
            status = "partial"
            failure_reason = "UNSTRUCTURED_INPUT"
            summary = f"附件 {file_path.name} 需远程 OCR 或可读文本才能抽取字段"
        elif not parsed_fields and text.strip():
            status = "partial"
            failure_reason = "NO_FIELDS_EXTRACTED"
            summary = text[:120] if text else f"已读取 {file_path.name}，未匹配到发票字段"
        else:
            status = "ok"
            failure_reason = None
            if parsed_fields:
                parts = [f"{key}={value}" for key, value in parsed_fields.items()]
                summary = "; ".join(parts)
            else:
                summary = text[:120] if text else f"已处理附件 {file_path.name}"

        return OcrAttachmentResult(
            attachment_id=str(attachment.get("attachment_id") or file_path.stem),
            file_name=str(attachment.get("file_name") or file_path.name),
            doc_uri=doc_uri,
            provider=provider,
            extracted_text=text,
            summary=summary,
            parsed_fields=parsed_fields,
            confidence=confidence,
            status=status,
            failure_reason=failure_reason,
        )

    def _resolve_local_path(self, *, user_id: str, attachment: dict) -> Path | None:
        file_url = str(attachment.get("file_url") or "").strip()
        if not file_url.startswith("/uploads/"):
            return None
        relative = file_url.removeprefix("/uploads/").split("/")
        if len(relative) < 2 or relative[0] != user_id:
            return None
        upload_root = Path(self._settings.upload_dir).expanduser().resolve()
        return upload_root.joinpath(*relative)

    def _try_remote_ocr(self, file_path: Path) -> str:
        remote_url = getattr(self._settings, "remote_ocr_url", None)
        if not remote_url:
            return ""

        boundary = f"----FinancialCoAgent{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        file_bytes = file_path.read_bytes()
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                file_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if getattr(self._settings, "remote_ocr_token", None):
            headers["Authorization"] = f"Bearer {self._settings.remote_ocr_token}"
        req = request.Request(remote_url, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return ""
        if isinstance(payload, dict):
            for key in ("text", "full_text", "content"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return ""

    @staticmethod
    def _extract_local_text(file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix in {".txt", ".md", ".csv", ".json"}:
            try:
                return file_path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                return file_path.read_text(encoding="utf-8", errors="ignore").strip()
        return f"Attachment ready for OCR: {file_path.name}"

    @staticmethod
    def _extract_invoice_fields(text: str) -> dict[str, str]:
        fields: dict[str, str] = {}

        invoice_number_patterns = [
            r"(?:发票号码|票据号码|invoice\s*number)[:：\s]*([A-Za-z0-9\-]+)",
            r"(?:发票号|票据号)[:：\s]*([A-Za-z0-9\-]+)",
        ]
        amount_patterns = [
            r"(?:金额|价税合计|total)[:：\s]*([0-9]+(?:\.[0-9]{1,2})?)",
            r"([0-9]+(?:\.[0-9]{1,2})?)\s*(?:元|yuan|cny)",
        ]

        for pattern in invoice_number_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                fields["invoice_number"] = match.group(1)
                break

        for pattern in amount_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                fields["amount"] = match.group(1)
                break

        lowered = text.lower()
        if "usd" in lowered or "美元" in text:
            fields["currency"] = "USD"
        elif "eur" in lowered or "欧元" in text:
            fields["currency"] = "EUR"
        elif fields.get("amount"):
            fields["currency"] = "CNY"

        return fields

    @staticmethod
    def _infer_field_confidence(parsed_fields: dict[str, str], extracted_text: str) -> dict[str, float]:
        """对抽取字段给出启发式置信度，供上游与审计使用。"""
        conf: dict[str, float] = {}
        lowered = extracted_text.lower()
        if "invoice_number" in parsed_fields:
            conf["invoice_number"] = 0.86
        if "amount" in parsed_fields:
            conf["amount"] = 0.84
        if "currency" in parsed_fields:
            cur = parsed_fields["currency"]
            if cur == "CNY":
                if "usd" in lowered or "美元" in extracted_text:
                    conf["currency"] = 0.4
                elif "eur" in lowered or "欧元" in extracted_text:
                    conf["currency"] = 0.4
                elif "元" in extracted_text or "rmb" in lowered or "cny" in lowered:
                    conf["currency"] = 0.78
                else:
                    conf["currency"] = 0.55
            else:
                conf["currency"] = 0.80
        return conf


ocr_service = OcrService()
