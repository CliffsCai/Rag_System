# -*- coding: utf-8 -*-
"""
PDF / Word 图文解析服务
切片 content 中直接嵌入图片占位符，大模型可感知图片位置。
图片上传 OSS（只存 oss_key，URL 查询时动态生成）
"""

import io
import re
import uuid
import logging
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF
from docx import Document as DocxDocument

fitz.TOOLS.mupdf_display_errors(False)

from app.services.oss_service import get_oss_service

logger = logging.getLogger(__name__)

_IMAGE_RE = re.compile(r"<<IMAGE:[0-9a-f]+>>")
_SENTENCE_ENDS = re.compile(r"[。？！.?!\n]")
_LIST_ITEM_RE = re.compile(r"^[（(]\d+[）)]|^[①②③④⑤⑥⑦⑧⑨⑩]|^[a-zA-Z]\.")
_TRANSITION_STARTS = ("但", "然而", "除外", "不包括", "不含", "除非", "但是", "否则", "注意", "⚠", "警告")


def _file_base(file_name: str) -> str:
    return file_name.rsplit(".", 1)[0] if "." in file_name else file_name


def _upload_image(image_bytes: bytes, ext: str, collection: str, file_name: str, chunk_id: str) -> str:
    """上传图片到 OSS，路径：rag_image/{collection}/{file_name}/{chunk_id}/{uuid}.{ext}"""
    oss_svc = get_oss_service()
    filename = f"{uuid.uuid4().hex[:12]}.{ext}"
    oss_key = oss_svc.upload_file(f"rag_image/{collection}/{file_name}/{chunk_id}", filename, image_bytes)
    return oss_key


def _smart_overlap(text: str, overlap_size: int) -> str:
    """取 text 末尾约 overlap_size 字符，从最近句子边界之后开始，保证 overlap 是完整句子。"""
    if overlap_size <= 0 or len(text) <= overlap_size:
        return ""
    tail = text[-(overlap_size * 2):]
    matches = list(_SENTENCE_ENDS.finditer(tail))
    if matches:
        candidate = tail[matches[-1].end():].lstrip()
        if candidate:
            return candidate
    return text[-overlap_size:]


def _should_merge(text1: str, text2: str) -> bool:
    """判断两个相邻 chunk 是否语义断裂，需要合并。"""
    c1 = _IMAGE_RE.sub("", text1).strip()
    c2 = _IMAGE_RE.sub("", text2).strip()
    if not c1 or not c2:
        return False
    if c1.endswith((":", "：", ";", "；")):
        return True
    if _LIST_ITEM_RE.match(c2):
        return True
    if c2.startswith(_TRANSITION_STARTS):
        return True
    return False


def _post_process(
    chunks: List[Dict],
    image_records: List[Dict],
    file_base: str,
) -> Tuple[List[Dict], List[Dict]]:
    """
    should_merge：合并语义断裂的相邻 chunk，同步更新 image_records 里的 chunk_id。
    chunk_id 保持原始 {job_id}_{idx} 不变，file_base 仅用于 merge 后的日志。
    """
    if not chunks:
        return chunks, image_records

    merged: List[Dict] = [chunks[0]]
    for cur in chunks[1:]:
        prev = merged[-1]
        if _should_merge(prev["content"], cur["content"]):
            old_cid = cur["chunk_id"]
            prev["content"] += cur["content"]
            # 合并后 image_records 里属于被合并 chunk 的记录，chunk_id 改为前者
            for rec in image_records:
                if rec["chunk_id"] == old_cid:
                    rec["chunk_id"] = prev["chunk_id"]
            logger.debug(f"[Merge] {file_base}: 合并 chunk {old_cid} → {prev['chunk_id']}")
        else:
            merged.append(cur)

    return merged, image_records


def parse_pdf(
    file_content: bytes,
    job_id: str,
    collection: str,
    file_name: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    image_dpi: int = 150,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    解析 PDF，切片 content 中直接嵌入图片占位符。

    流程：
    1. 按页提取文字块和图片块（图片只暂存字节，不在此阶段上传）
    2. 按 (page, y_center) 排序成文字-图片交织序列
    3. 单次遍历切分，图片分配到具体 chunk 后再上传 OSS
    4. 后处理：should_merge + 重分配 chunk_id + prev/next
    """
    doc = fitz.open(stream=file_content, filetype="pdf")

    # ── 提取所有元素 ──────────────────────────────────────────────────────────
    elements: List[Dict] = []

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
                # 只暂存字节，切分阶段确定 chunk_id 后再上传
                elements.append({
                    "type": "image",
                    "page": page_num,
                    "y_center": y_center,
                    "img_bytes": img_bytes,
                    "ext": ext,
                })
            except Exception as e:
                logger.warning(f"[Parser] 图片提取失败 page={page_num} xref={xref}: {e}")

    doc.close()

    elements.sort(key=lambda e: (e["page"], e["y_center"]))
    logger.info(f"[Parser] 文字块 {sum(1 for e in elements if e['type']=='text')} 个，"
                f"图片 {sum(1 for e in elements if e['type']=='image')} 张")

    # ── 切分 ──────────────────────────────────────────────────────────────────
    file_base = _file_base(file_name)
    chunks: List[Dict] = []
    image_records: List[Dict] = []

    buffer = ""
    text_len = 0
    chunk_idx = 0
    img_sort = 0
    overlap_buf = ""
    first_page = None

    def _chunk_id():
        # 临时 id，后处理会重新分配
        return f"{file_base}_{chunk_idx}"

    def _seal():
        nonlocal buffer, text_len, chunk_idx, img_sort, overlap_buf, first_page
        if buffer.strip():
            chunks.append({
                "chunk_id": _chunk_id(),
                "content": buffer,
                "metadata": {
                    "page": first_page,
                    "chunk_id": _chunk_id(),
                    "prev_chunk_id": None,
                    "next_chunk_id": None,
                },
            })
            text_only = _IMAGE_RE.sub("", buffer)
            overlap_buf = _smart_overlap(text_only, chunk_overlap)
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

        elif elem["type"] == "image":
            if not buffer and overlap_buf:
                buffer = overlap_buf
                text_len = len(overlap_buf)
                overlap_buf = ""

            # chunk_idx 已确定，现在上传
            current_chunk_id = _chunk_id()
            try:
                oss_key = _upload_image(
                    elem["img_bytes"], elem["ext"],
                    collection, file_name, current_chunk_id,
                )
            except Exception as e:
                logger.warning(f"[Parser] 图片上传失败: {e}")
                continue

            placeholder = f"<<IMAGE:{uuid.uuid4().hex[:8]}>>"
            buffer += placeholder
            image_records.append({
                "id": str(uuid.uuid4()),
                "chunk_id": current_chunk_id,
                "job_id": job_id,
                "placeholder": placeholder,
                "oss_key": oss_key,
                "page": elem["page"],
                "sort_order": img_sort,
            })
            img_sort += 1
            logger.info(f"[Parser] 图片上传: {oss_key} page={elem['page']}")

    if buffer.strip():
        chunks.append({
            "chunk_id": _chunk_id(),
            "content": buffer,
            "metadata": {
                "page": first_page,
                "chunk_id": _chunk_id(),
                "prev_chunk_id": None,
                "next_chunk_id": None,
            },
        })

    # ── 后处理 ────────────────────────────────────────────────────────────────
    chunks, image_records = _post_process(chunks, image_records, file_base)
    logger.info(f"[Parser] 完成: {len(chunks)} 个切片, {len(image_records)} 条图片记录")
    return chunks, image_records


def parse_word(
    file_content: bytes,
    job_id: str,
    collection: str,
    file_name: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    解析 Word (.docx)，切片 content 中直接嵌入图片占位符。
    Word 无页码，metadata.page 固定为 None。
    """
    doc = DocxDocument(io.BytesIO(file_content))

    W_NS    = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    A_NS    = "http://schemas.openxmlformats.org/drawingml/2006/main"
    W_P     = f"{{{W_NS}}}p"
    W_T     = f"{{{W_NS}}}t"
    A_BLIP  = f"{{{A_NS}}}blip"
    R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"

    file_base = _file_base(file_name)
    chunks: List[Dict] = []
    image_records: List[Dict] = []

    buffer = ""
    text_len = 0
    chunk_idx = 0
    img_sort = 0
    overlap_buf = ""
    bound_rids: set = set()

    def _chunk_id():
        return f"{file_base}_{chunk_idx}"

    def _seal():
        nonlocal buffer, text_len, chunk_idx, img_sort, overlap_buf
        if buffer.strip():
            chunks.append({
                "chunk_id": _chunk_id(),
                "content": buffer,
                "metadata": {
                    "page": None,
                    "chunk_id": _chunk_id(),
                    "prev_chunk_id": None,
                    "next_chunk_id": None,
                },
            })
            text_only = _IMAGE_RE.sub("", buffer)
            overlap_buf = _smart_overlap(text_only, chunk_overlap)
        chunk_idx += 1
        img_sort = 0
        buffer = ""
        text_len = 0

    def _insert_image(r_id: str):
        nonlocal img_sort, buffer
        if r_id in bound_rids:
            return
        try:
            img_part = doc.part.related_parts[r_id]
            img_bytes = img_part.blob
            if len(img_bytes) < 1000:
                return
            ct = img_part.content_type
            ext = ct.split("/")[-1].replace("jpeg", "jpg")
            oss_key = _upload_image(img_bytes, ext, collection, file_name, _chunk_id())
            placeholder = f"<<IMAGE:{uuid.uuid4().hex[:8]}>>"
            buffer += placeholder
            image_records.append({
                "id": str(uuid.uuid4()),
                "chunk_id": _chunk_id(),
                "job_id": job_id,
                "placeholder": placeholder,
                "oss_key": oss_key,
                "page": None,
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
            "metadata": {
                "page": None,
                "chunk_id": _chunk_id(),
                "prev_chunk_id": None,
                "next_chunk_id": None,
            },
        })

    chunks, image_records = _post_process(chunks, image_records, file_base)
    logger.info(f"[WordParser] 完成: {len(chunks)} 个切片, {len(image_records)} 条图片记录")
    return chunks, image_records
