# -*- coding: utf-8 -*-
"""
纯文本切分器（标准模式）
中文友好，支持句子边界 overlap，复用图文模式的 should_merge 逻辑
"""
import io
import re
from typing import List, Tuple

# 句子结束符（用于 overlap 从句子边界开始）
_SENTENCE_END = re.compile(r'[。！？.!?]')

# 段落分隔符优先级（从粗到细）
_SEPARATORS = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", "，", ",", " ", ""]

# 列表项开头（用于 should_merge 检测）
_LIST_PREFIX = re.compile(r'^[\s]*[①②③④⑤⑥⑦⑧⑨⑩\-\*•◆▶➤]|^\s*\d+[\.、\)）]')
# 转折词开头
_TRANSITION_START = re.compile(r'^(但是|然而|不过|此外|另外|同时|因此|所以|综上|总之|首先|其次|最后|另一方面)')


def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[str]:
    """
    将文本切分为 chunks。
    1. 按分隔符递归切分到 chunk_size 以内
    2. 合并过短的片段
    3. should_merge：检测语义断裂，合并相邻 chunk
    4. 添加 overlap
    """
    if not text or not text.strip():
        return []

    raw_chunks = _recursive_split(text.strip(), chunk_size)
    merged = _merge_short(raw_chunks, chunk_size)
    merged = _should_merge(merged, chunk_size)
    result = _add_overlap(merged, chunk_overlap)
    return [c for c in result if c.strip()]


def split_text_with_metadata(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    base_metadata: dict = None,
) -> List[dict]:
    """返回带 metadata 的 chunk 列表，格式与图文模式一致"""
    chunks = split_text(text, chunk_size, chunk_overlap)
    meta = base_metadata or {}
    return [
        {"content": c, "metadata": {**meta, "chunk_index": i}}
        for i, c in enumerate(chunks)
    ]


# ── 内部实现 ──────────────────────────────────────────────────────────────────

def _recursive_split(text: str, chunk_size: int) -> List[str]:
    """递归按分隔符切分，直到每段 <= chunk_size"""
    if len(text) <= chunk_size:
        return [text]

    for sep in _SEPARATORS:
        if sep == "":
            # 最后手段：按字符硬切
            return [text[i: i + chunk_size] for i in range(0, len(text), chunk_size)]
        if sep in text:
            parts = text.split(sep)
            result = []
            current = ""
            for part in parts:
                candidate = current + (sep if current else "") + part
                if len(candidate) <= chunk_size:
                    current = candidate
                else:
                    if current:
                        result.append(current)
                    if len(part) > chunk_size:
                        result.extend(_recursive_split(part, chunk_size))
                        current = ""
                    else:
                        current = part
            if current:
                result.append(current)
            return result

    return [text]


def _merge_short(chunks: List[str], chunk_size: int, min_size: int = 50) -> List[str]:
    """将过短的 chunk 合并到前一个"""
    if not chunks:
        return []
    result = [chunks[0]]
    for chunk in chunks[1:]:
        if len(chunk) < min_size and len(result[-1]) + len(chunk) <= chunk_size:
            result[-1] = result[-1] + chunk
        else:
            result.append(chunk)
    return result


def _should_merge(chunks: List[str], chunk_size: int) -> List[str]:
    """
    检测语义断裂并合并：
    - 上一个 chunk 以冒号结尾
    - 当前 chunk 以列表项开头
    - 当前 chunk 以转折词开头
    合并后若超过 chunk_size 则不合并
    """
    if len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for chunk in chunks[1:]:
        prev = result[-1]
        should = (
            prev.rstrip().endswith(("：", ":"))
            or _LIST_PREFIX.match(chunk)
            or _TRANSITION_START.match(chunk)
        )
        if should and len(prev) + len(chunk) <= chunk_size * 1.5:
            result[-1] = prev + chunk
        else:
            result.append(chunk)
    return result


def _add_overlap(chunks: List[str], overlap: int) -> List[str]:
    """
    在每个 chunk 开头加上前一个 chunk 末尾的 overlap 字符。
    从句子边界开始，不在词中间截断。
    """
    if overlap <= 0 or len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        tail = prev[-overlap:] if len(prev) > overlap else prev
        # 从句子边界开始
        m = _SENTENCE_END.search(tail)
        if m:
            tail = tail[m.end():]
        if tail.strip():
            result.append(tail + chunks[i])
        else:
            result.append(chunks[i])
    return result


# ── Excel 切分 ────────────────────────────────────────────────────────────────

def split_excel(
    file_content: bytes,
    file_name: str,
    rows_per_chunk: int = 50,
    base_metadata: dict = None,
) -> List[dict]:
    """
    将 Excel 文件按 sheet 切分为 chunks。

    规则：
    - 每个 sheet 独立处理，不同 sheet 的数据不混入同一切片
    - 每个切片包含：文件名 + sheet 名（标题增强）+ 表头行 + 数据行
    - 若某 sheet 剩余行数不足 rows_per_chunk，单独成一个切片（不跨 sheet 补齐）
    - 空 sheet（无数据行）跳过

    切片 content 格式：
        文件：{file_name}  Sheet：{sheet_name}
        {col1}\t{col2}\t...
        {val1}\t{val2}\t...
        ...
    """
    import pandas as pd

    meta = base_metadata or {}
    chunks = []
    chunk_index = 0

    # read_excel 返回 {sheet_name: DataFrame}，header=0 默认第一行为列名
    sheets: dict = pd.read_excel(
        io.BytesIO(file_content),
        sheet_name=None,   # 读取所有 sheet
        header=0,
        dtype=str,         # 统一转字符串，避免数值/日期格式问题
        keep_default_na=False,
    )

    for sheet_name, df in sheets.items():
        # 去掉全空行
        df = df.dropna(how="all").reset_index(drop=True)
        if df.empty:
            continue

        # 列名列表（表头）
        headers = list(df.columns)
        header_line = "\t".join(str(h) for h in headers)

        # 标题前缀：每个切片都带上文件名和 sheet 名
        title_prefix = f"文件：{file_name}  Sheet：{sheet_name}\n"

        total_rows = len(df)
        start = 0
        while start < total_rows:
            end = min(start + rows_per_chunk, total_rows)
            rows = df.iloc[start:end]

            # 拼接内容：标题前缀 + 表头 + 数据行
            lines = [title_prefix + header_line]
            for _, row in rows.iterrows():
                lines.append("\t".join(str(v) for v in row))
            content = "\n".join(lines)

            chunks.append({
                "content": content,
                "metadata": {
                    **meta,
                    "chunk_index": chunk_index,
                    "file_name": file_name,
                    "sheet_name": sheet_name,
                    "source": "excel",
                    "row_start": start,
                    "row_end": end - 1,
                },
            })
            chunk_index += 1
            start = end

    return chunks
