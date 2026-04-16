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
    column_config: dict = None,
) -> List[dict]:
    """
    将 Excel 文件按 sheet 切分为 chunks。

    column_config 格式（每文件独立，由前端传入）：
        {
          "Sheet1": [
            {"original": "省份", "alias": "省份"},
            {"original": "城市", "alias": "城市"},
            ...
          ],
          "Sheet2": [...]
        }
    None 表示全选、不改名。

    切片 content 格式（key=value，每行一条记录）：
        文件：{file_name}  Sheet：{sheet_name}
        省份=浙江, 城市=杭州, SN=530129
        省份=山东, 城市=聊城, SN=33318
        ...
    """
    import pandas as pd

    meta = base_metadata or {}
    chunks = []
    chunk_index = 0

    sheets: dict = pd.read_excel(
        io.BytesIO(file_content),
        sheet_name=None,
        header=0,
        dtype=str,
        keep_default_na=False,
    )

    for sheet_name, df in sheets.items():
        df = df.dropna(how="all").reset_index(drop=True)
        if df.empty:
            continue

        # 确定本 sheet 使用的列配置
        sheet_cfg = None
        if column_config and sheet_name in column_config:
            sheet_cfg = column_config[sheet_name]  # [{original, alias}, ...]

        if sheet_cfg is not None:
            # 只保留配置中存在于 df 的列
            valid_cols = [c for c in sheet_cfg if c["original"] in df.columns]
            if not valid_cols:
                continue
            orig_cols = [c["original"] for c in valid_cols]
            alias_map = {c["original"]: c["alias"] or c["original"] for c in valid_cols}
            df = df[orig_cols]
        else:
            # 全选，alias = original
            orig_cols = list(df.columns)
            alias_map = {c: c for c in orig_cols}

        title_prefix = f"文件：{file_name}  Sheet：{sheet_name}\n"
        total_rows = len(df)
        start = 0

        while start < total_rows:
            end = min(start + rows_per_chunk, total_rows)
            rows = df.iloc[start:end]

            # 每行格式：alias1=val1, alias2=val2, ...
            lines = []
            for _, row in rows.iterrows():
                parts = []
                for col in orig_cols:
                    val = str(row[col]).strip()
                    if val:  # 跳过空值，减少噪音
                        parts.append(f"{alias_map[col]}={val}")
                if parts:
                    lines.append(", ".join(parts))

            if not lines:
                start = end
                continue

            content = title_prefix + "\n".join(lines)

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
