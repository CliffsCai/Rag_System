# -*- coding: utf-8 -*-
"""
PDF / Word 图文解析服务
切片 content 中直接嵌入图片占位符，大模型可感知图片位置。
图片上传 OSS（只存 oss_key，URL 查询时动态生成）
"""

import io
import uuid
import logging
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF
from docx import Document as DocxDocument

fitz.TOOLS.mupdf_display_errors(False)

from app.services.oss_service import get_oss_service

logger = logging.getLogger(__name__)


def _upload_image(image_bytes: bytes, ext: str, job_id: str) -> str:
    """上传图片到 OSS，返回 oss_key"""
    oss_svc = get_oss_service()
    filename = f"{uuid.uuid4().hex[:12]}.{ext}"
    oss_key = oss_svc.upload_file(f"rag_knowledge/images/{job_id}", filename, image_bytes)
    return oss_key


def parse_pdf(
    file_content: bytes,
    job_id: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    image_dpi: int = 150,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    解析 PDF，切片 content 中直接嵌入图片占位符。

    流程：
    1. 按页提取文字块和图片块，统一按 (page, y_center) 排序成交织序列
    2. 单次遍历：文字追加到 buffer 计字符数，图片占位符直接插入 buffer（不计字符数）
    3. buffer 达到 chunk_size 时封存，overlap 只保留文字部分

    Returns:
        chunks: [{"chunk_id": str, "content": str, "metadata": dict}]
        image_records: [{"id": str, "chunk_id": str, "job_id": str, "placeholder": str,
                         "oss_key": str, "page": int, "sort_order": int}]
    """
    doc = fitz.open(stream=file_content, filetype="pdf")

    # ── 提取所有元素（文字块 + 图片块），统一排序 ────────────────────────────
    elements: List[Dict] = []  # {"type": "text"|"image", "page", "y_center", ...}

    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]
        blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

        for b in blocks:
            if b["type"] != 0:
                continue
            text = "".join(
                span["text"]
                for line in b.get("lines", [])
                for span in line.get("spans", [])
            ).strip()
            if text:
                y_center = (b["bbox"][1] + b["bbox"][3]) / 2
                elements.append({
                    "type": "text",
                    "page": page_num,
                    "y_center": y_center,
                    "y_min": b["bbox"][1],
                    "y_max": b["bbox"][3],
                    "text": text,
                })

        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                ext = base_image.get("ext", "png")
                if len(img_bytes) < 1000:
                    continue
                img_rects = page.get_image_rects(xref)
                if not img_rects:
                    continue
                y_center = (img_rects[0].y0 + img_rects[0].y1) / 2
                oss_key = _upload_image(img_bytes, ext, job_id)
                placeholder = f"<<IMAGE:{uuid.uuid4().hex[:8]}>>"
                elements.append({
                    "type": "image",
                    "page": page_num,
                    "y_center": y_center,
                    "placeholder": placeholder,
                    "oss_key": oss_key,
                })
                logger.info(f"[Parser] 图片已上传: {oss_key} page={page_num} xref={xref}")
            except Exception as e:
                logger.warning(f"[Parser] 图片提取失败 page={page_num} xref={xref}: {e}")

    doc.close()

    # 按页码 + y 坐标排序，得到文字-图片交织序列
    elements.sort(key=lambda e: (e["page"], e["y_center"]))
    text_count = sum(1 for e in elements if e["type"] == "text")
    img_count = sum(1 for e in elements if e["type"] == "image")
    logger.info(f"[Parser] 共 {text_count} 个文字块，{img_count} 张图片")

    # ── 单次遍历切分 ──────────────────────────────────────────────────────────
    chunks: List[Dict] = []
    image_records: List[Dict] = []

    buffer = ""          # 当前 chunk 内容（含占位符）
    text_len = 0         # 只统计文字字符数，不含占位符
    chunk_idx = 0
    img_sort = 0
    overlap_buf = ""     # overlap 文字（不含占位符）
    first_page = None    # 当前 chunk 首页

    def _chunk_id():
        return f"{job_id}_{chunk_idx}"

    def _seal():
        nonlocal buffer, text_len, chunk_idx, img_sort, overlap_buf, first_page
        if buffer.strip():
            chunks.append({
                "chunk_id": _chunk_id(),
                "content": buffer,
                "metadata": {"page": first_page},
            })
            # overlap 只取纯文字部分（去掉占位符）
            import re
            text_only = re.sub(r"<<IMAGE:[0-9a-f]+>>", "", buffer)
            overlap_buf = text_only[-chunk_overlap:] if chunk_overlap > 0 and len(text_only) > chunk_overlap else ""
        chunk_idx += 1
        img_sort = 0
        buffer = ""
        text_len = 0
        first_page = None

    for elem in elements:
        if elem["type"] == "text":
            text = elem["text"]
            if first_page is None:
                first_page = elem["page"]

            # 新 chunk 开头填入 overlap
            if not buffer and overlap_buf:
                buffer = overlap_buf
                text_len = len(overlap_buf)
                overlap_buf = ""

            # 文字可能需要分段填入（超出 chunk_size 时）
            remaining = text
            while remaining:
                space = chunk_size - text_len
                part = remaining[:space]
                buffer += part
                text_len += len(part)
                remaining = remaining[space:]
                if text_len >= chunk_size:
                    _seal()
                    if remaining and overlap_buf:
                        buffer = overlap_buf
                        text_len = len(overlap_buf)
                        overlap_buf = ""

        elif elem["type"] == "image":
            placeholder = elem["placeholder"]
            oss_key = elem["oss_key"]

            # 图片在文字之前时兜底
            if not buffer and overlap_buf:
                buffer = overlap_buf
                text_len = len(overlap_buf)
                overlap_buf = ""

            # 占位符直接插入 buffer，不计字符数
            buffer += placeholder
            image_records.append({
                "id": str(uuid.uuid4()),
                "chunk_id": _chunk_id(),
                "job_id": job_id,
                "placeholder": placeholder,
                "oss_key": oss_key,
                "page": elem["page"],
                "sort_order": img_sort,
            })
            img_sort += 1

    # 封存最后一个 chunk
    if buffer.strip():
        chunks.append({
            "chunk_id": _chunk_id(),
            "content": buffer,
            "metadata": {"page": first_page},
        })

    logger.info(f"[Parser] 完成: {len(chunks)} 个切片, {len(image_records)} 条图片记录")
    return chunks, image_records


def parse_word(
    file_content: bytes,
    job_id: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    解析 Word (.docx)，切片 content 中直接嵌入图片占位符。

    单次 iter() 遍历：文字计字符数，图片占位符直接插入 buffer（不计字符数）。
    overlap 只保留文字部分，图片不重复绑定（rId 全局去重）。
    """
    import re
    doc = DocxDocument(io.BytesIO(file_content))

    W_NS    = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    A_NS    = "http://schemas.openxmlformats.org/drawingml/2006/main"
    W_P     = f"{{{W_NS}}}p"
    W_T     = f"{{{W_NS}}}t"
    A_BLIP  = f"{{{A_NS}}}blip"
    R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"

    chunks: List[Dict] = []
    image_records: List[Dict] = []

    buffer = ""
    text_len = 0       # 只统计文字字符数
    chunk_idx = 0
    img_sort = 0
    overlap_buf = ""   # overlap 纯文字
    bound_rids: set = set()

    def _chunk_id():
        return f"{job_id}_{chunk_idx}"

    def _seal():
        nonlocal buffer, text_len, chunk_idx, img_sort, overlap_buf
        if buffer.strip():
            chunks.append({
                "chunk_id": _chunk_id(),
                "content": buffer,
                "metadata": {"page": 1},
            })
            text_only = re.sub(r"<<IMAGE:[0-9a-f]+>>", "", buffer)
            overlap_buf = text_only[-chunk_overlap:] if chunk_overlap > 0 and len(text_only) > chunk_overlap else ""
        chunk_idx += 1
        img_sort = 0
        buffer = ""
        text_len = 0

    def _insert_image(r_id: str):
        nonlocal img_sort
        if r_id in bound_rids:
            logger.info(f"[WordParser] rId={r_id} 已绑定（overlap），跳过")
            return
        try:
            img_part = doc.part.related_parts[r_id]
            img_bytes = img_part.blob
            if len(img_bytes) < 1000:
                logger.warning(f"[WordParser] 图片过小跳过 rId={r_id}")
                return
            ct = img_part.content_type
            ext = ct.split("/")[-1].replace("jpeg", "jpg")
            oss_key = _upload_image(img_bytes, ext, job_id)
            placeholder = f"<<IMAGE:{uuid.uuid4().hex[:8]}>>"

            # 占位符直接插入 buffer，不计字符数
            nonlocal buffer
            buffer += placeholder
            image_records.append({
                "id": str(uuid.uuid4()),
                "chunk_id": _chunk_id(),
                "job_id": job_id,
                "placeholder": placeholder,
                "oss_key": oss_key,
                "page": 1,
                "sort_order": img_sort,
            })
            bound_rids.add(r_id)
            img_sort += 1
            logger.info(f"[WordParser] 图片插入 chunk {_chunk_id()} rId={r_id}")
        except Exception as e:
            logger.warning(f"[WordParser] 图片提取失败 rId={r_id}: {e}")

    for node in doc.element.body.iter():
        if node.tag == W_P:
            text = "".join(
                child.text or "" for child in node.iter() if child.tag == W_T
            ).strip()
            if not text:
                continue

            if not buffer and overlap_buf:
                buffer = overlap_buf
                text_len = len(overlap_buf)
                overlap_buf = ""

            remaining = text
            while remaining:
                space = chunk_size - text_len
                part = remaining[:space]
                buffer += part
                text_len += len(part)
                remaining = remaining[space:]
                if text_len >= chunk_size:
                    _seal()
                    if remaining and overlap_buf:
                        buffer = overlap_buf
                        text_len = len(overlap_buf)
                        overlap_buf = ""

        elif node.tag == A_BLIP:
            r_id = node.get(R_EMBED)
            if not r_id:
                continue
            if not buffer and overlap_buf:
                buffer = overlap_buf
                text_len = len(overlap_buf)
                overlap_buf = ""
            _insert_image(r_id)

    if buffer.strip():
        chunks.append({
            "chunk_id": _chunk_id(),
            "content": buffer,
            "metadata": {"page": 1},
        })

    logger.info(f"[WordParser] 完成: {len(chunks)} 个切片, {len(image_records)} 条图片记录")
    return chunks, image_records
