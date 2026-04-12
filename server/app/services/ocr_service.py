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
    attachment_id: str
    file_name: str
    provider: str
    extracted_text: str
    summary: str
    parsed_fields: dict[str, str]


class OcrService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def analyze_attachments(self, *, user_id: str, attachments: list[dict]) -> list[OcrAttachmentResult]:
        results: list[OcrAttachmentResult] = []
        for attachment in attachments:
            file_path = self._resolve_local_path(user_id=user_id, attachment=attachment)
            if not file_path or not file_path.exists():
                continue
            results.append(self._analyze_file(file_path=file_path, attachment=attachment))
        return results

    def _analyze_file(self, *, file_path: Path, attachment: dict) -> OcrAttachmentResult:
        remote_text = self._try_remote_ocr(file_path)
        if remote_text:
            text = remote_text.strip()
            provider = "remote_ocr"
        else:
            text = self._extract_local_text(file_path)
            provider = "local_fallback"

        parsed_fields = self._extract_invoice_fields(text)
        if parsed_fields:
            parts = [f"{key}={value}" for key, value in parsed_fields.items()]
            summary = "; ".join(parts)
        else:
            summary = text[:120] if text else f"Processed attachment {file_path.name}"
        return OcrAttachmentResult(
            attachment_id=str(attachment.get("attachment_id") or file_path.stem),
            file_name=str(attachment.get("file_name") or file_path.name),
            provider=provider,
            extracted_text=text,
            summary=summary,
            parsed_fields=parsed_fields,
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


ocr_service = OcrService()
