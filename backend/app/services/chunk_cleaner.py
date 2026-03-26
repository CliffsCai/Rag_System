# -*- coding: utf-8 -*-
"""
切片清洗服务
使用 LLM 清洗文档切片，去除水印、页码、页眉页脚等
"""

import logging
import re
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
import httpx
import ssl

logger = logging.getLogger(__name__)


def get_llm_client(model_name: str = "qwen-plus"):
    """
    获取 LLM 客户端
    
    Args:
        model_name: 模型名称
        
    Returns:
        ChatOpenAI 客户端
    """
    if not settings.ssl_verify:
        ssl._create_default_https_context = ssl._create_unverified_context
    
    http_client = httpx.Client(
        verify=settings.ssl_verify,
        timeout=settings.timeout
    )
    
    return ChatOpenAI(
        model=model_name,
        temperature=0.1,  # 低温度，保持内容准确性
        base_url=settings.dashscope_base_url,
        api_key=settings.dashscope_api_key,
        streaming=False,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
        http_client=http_client
    )


def clean_chunk_with_regex(content: str) -> str:
    """
    使用正则表达式进行基础清洗
    
    Args:
        content: 原始内容
        
    Returns:
        清洗后的内容
    """
    # 去除页码
    content = re.sub(r'第\s*\d+\s*页', '', content)
    content = re.sub(r'Page\s+\d+', '', content, flags=re.IGNORECASE)
    content = re.sub(r'^\s*\d+\s*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'-\s*\d+\s*-', '', content)
    
    # 去除常见页眉页脚
    content = re.sub(r'^[\s\-_=]+$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*第[一二三四五六七八九十百千万\d]+章.*$', '', content, flags=re.MULTILINE)
    
    # 去除水印相关
    content = re.sub(r'仅供.*?参考', '', content)
    content = re.sub(r'内部资料.*?外传', '', content)
    content = re.sub(r'机密.*?文件', '', content)
    
    # 去除多余空白
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r' {3,}', '  ', content)
    content = content.strip()
    
    return content


def clean_chunks_with_llm(
    chunks: List[Dict[str, Any]],
    clean_type: str = "batch"
) -> List[Dict[str, Any]]:
    """
    使用 LLM 清洗切片内容
    
    Args:
        chunks: 切片列表
        clean_type: 清洗类型（batch=批量, single=单个）
        
    Returns:
        清洗后的切片列表
    """
    try:
        logger.info(f"[ChunkCleaner] 开始清洗 {len(chunks)} 个切片，类型: {clean_type}")
        
        # 先用正则表达式做基础清洗
        for chunk in chunks:
            if 'content' in chunk:
                chunk['content'] = clean_chunk_with_regex(chunk['content'])
        
        # 如果是批量清洗，使用 LLM 进一步优化
        if clean_type == "batch" and len(chunks) > 0:
            cleaned_chunks = batch_clean_with_llm(chunks)
        else:
            # 单个清洗或不使用 LLM
            cleaned_chunks = chunks
        
        logger.info(f"[ChunkCleaner] 清洗完成，共 {len(cleaned_chunks)} 个切片")
        return cleaned_chunks
        
    except Exception as e:
        logger.error(f"[ChunkCleaner] 清洗失败: {str(e)}")
        # 失败时返回正则清洗后的结果
        return chunks


def batch_clean_with_llm(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    批量使用 LLM 清洗切片
    
    Args:
        chunks: 切片列表
        
    Returns:
        清洗后的切片列表
    """
    try:
        llm = get_llm_client()
        cleaned_chunks = []
        
        # 每次处理 5 个切片
        batch_size = 5
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            logger.info(f"[ChunkCleaner] 处理批次 {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")
            
            # 构建批量清洗提示
            batch_content = []
            for j, chunk in enumerate(batch):
                batch_content.append(f"=== 切片 {j+1} ===\n{chunk.get('content', '')}")
            
            combined_content = "\n\n".join(batch_content)
            
            system_prompt = """你是一个专业的文档清洗助手。你的任务是清洗文档切片，去除：
1. 水印文字（如"仅供参考"、"内部资料"等）
2. 页码（如"第1页"、"Page 1"、"-1-"等）
3. 页眉页脚（如章节标题、分隔线等）
4. 修正明显的 OCR 错误
5. 去除多余的空白和换行

要求：
- 保持原文的核心内容和含义不变
- 保持专业术语的准确性
- 保持原有的段落结构
- 不要添加任何新内容
- 每个切片单独处理，用 "=== 切片 N ===" 分隔

请对以下切片进行清洗："""
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=combined_content)
            ]
            
            try:
                response = llm.invoke(messages)
                cleaned_content = response.content
                
                # 解析清洗后的切片
                cleaned_parts = re.split(r'===\s*切片\s+\d+\s*===', cleaned_content)
                cleaned_parts = [part.strip() for part in cleaned_parts if part.strip()]
                
                for j, chunk in enumerate(batch):
                    if j < len(cleaned_parts) and cleaned_parts[j]:
                        # 使用清洗后的内容
                        cleaned_chunk = {
                            "content": cleaned_parts[j],
                            "metadata": chunk.get("metadata", {})
                        }
                        if "id" in chunk:
                            cleaned_chunk["id"] = chunk["id"]
                        cleaned_chunks.append(cleaned_chunk)
                    else:
                        # 如果解析失败，保留原切片
                        cleaned_chunks.append(chunk)
                        
            except Exception as e:
                logger.error(f"[ChunkCleaner] 批次清洗失败: {str(e)}")
                # 失败时保留原切片
                cleaned_chunks.extend(batch)
        
        return cleaned_chunks
        
    except Exception as e:
        logger.error(f"[ChunkCleaner] LLM 清洗失败: {str(e)}")
        return chunks


def clean_single_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """
    清洗单个切片
    
    Args:
        chunk: 单个切片
        
    Returns:
        清洗后的切片
    """
    try:
        content = chunk.get('content', '')
        
        # 正则清洗
        cleaned_content = clean_chunk_with_regex(content)
        
        # 使用 LLM 进一步清洗
        llm = get_llm_client()
        
        system_prompt = """你是一个专业的文档清洗助手。请清洗以下文本，去除：
1. 水印文字
2. 页码
3. 页眉页脚
4. OCR 错误
5. 多余空白

保持原文核心内容不变，只返回清洗后的文本，不要添加任何说明。"""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=cleaned_content)
        ]
        
        response = llm.invoke(messages)
        final_content = response.content.strip()
        
        return {
            "content": final_content,
            "metadata": chunk.get("metadata", {}),
            "id": chunk.get("id")
        }
        
    except Exception as e:
        logger.error(f"[ChunkCleaner] 单个切片清洗失败: {str(e)}")
        return chunk


def clean_single_chunk_with_llm(content: str, instruction: str = None) -> str:
    """
    使用 LLM 清洗单个切片内容（供 API 层调用）

    Args:
        content: 切片原始内容
        instruction: 额外清洗指令（可选）

    Returns:
        清洗后的内容字符串
    """
    from dashscope import Generation
    from app.core.prompts import CHUNK_CLEAN_SYSTEM, CHUNK_CLEAN_PROMPT

    prompt = CHUNK_CLEAN_PROMPT.format(content=content)
    if instruction:
        prompt += f"\n\n额外要求：{instruction}"

    messages = [
        {"role": "system", "content": CHUNK_CLEAN_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    response = Generation.call(
        api_key=settings.dashscope_api_key,
        model=settings.llm_clean_model,
        messages=messages,
        result_format="message",
        temperature=0,
    )

    if response.status_code != 200:
        raise Exception(f"DashScope 调用失败: {response.code} - {response.message}")

    return response.output.choices[0].message.content.strip()
