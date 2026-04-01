from __future__ import annotations

from io import BytesIO


def parse_resume_file(filename: str, raw: bytes) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1]

    if suffix in {"txt", "md"}:
        return raw.decode("utf-8").strip()

    if suffix == "pdf":
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise RuntimeError("当前环境缺少 pypdf，无法读取 PDF 简历。") from exc

        reader = PdfReader(BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if not text:
            raise RuntimeError("PDF 已上传，但没有提取到可用文本。")
        return text

    raise RuntimeError("当前仅支持 txt / md / pdf 简历文件。")
