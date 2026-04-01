# 迁移指南：ADB PostgreSQL → Milvus + PostgreSQL

## 概述

本次迁移将原来的阿里云 ADB PostgreSQL（同时承担向量存储和业务数据存储）拆分为：

- **Milvus Standalone**（Docker）：向量存储 + 混合检索（dense + BM25）
- **PostgreSQL**（Docker）：业务数据存储（知识库配置、文件、任务、切片等）

数据不迁移，重新上传文件即可。

---

## 一、环境准备

### 1. 启动 Docker 服务

```bash
# 在项目根目录执行
docker-compose up -d
```

等待所有容器健康（约 30-60 秒）：

```bash
docker-compose ps
# 确认 milvus-etcd、milvus-minio、milvus-standalone、kb-postgres 均为 healthy
```

### 2. 配置环境变量

```bash
cd backend
cp .env.example .env
```

编辑 `.env`，填写以下必填项：

```env
# LLM（必填）
DASHSCOPE_API_KEY=sk-xxxx

# OSS（必填）
OSS_BUCKET=your-bucket-name
OSS_REGION=cn-shanghai
OSS_ENDPOINT=https://oss-cn-shanghai.aliyuncs.com
ALIBABA_CLOUD_ACCESS_KEY_ID=xxxx
ALIBABA_CLOUD_ACCESS_KEY_SECRET=xxxx

# Milvus（Docker 默认值，通常不需要改）
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_USER=root
MILVUS_PASSWORD=your_milvus_password

# PostgreSQL（Docker 默认值，通常不需要改）
PG_HOST=localhost
PG_PORT=5432
PG_DB=knowledge_db
PG_USER=your_pg_user
PG_PASSWORD=your_pg_password

# Embedding（可选，默认 text-embedding-v3）
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIMENSION=1536
EMBEDDING_BATCH_SIZE=20
```

### 3. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

主要变化：
- 移除：`alibabacloud-gpdb20160503`、`alibabacloud-tea-openapi`、`alibabacloud-tea-util`
- 新增：`pymilvus>=2.5.0`

---

## 二、初始化数据库

应用启动时会自动执行建表，也可以手动执行：

```bash
cd backend
python -m app.db.init_db
```

建表顺序（按外键依赖）：
1. `knowledge_base`
2. `knowledge_category`
3. `knowledge_category_file`
4. `knowledge_file`
5. `knowledge_job`
6. `knowledge_chunk`
7. `knowledge_chunk_origin`
8. `knowledge_chunk_image`

---

## 三、启动后端

```bash
cd backend
python main.py
```

启动日志应包含：
```
开始初始化数据库表...
数据库表初始化完成
应用启动完成
```

---

## 四、重新创建知识库

原来的知识库配置（ADB namespace/collection）已失效，需要重新创建。

### 创建知识库

```bash
curl -X POST http://localhost:8000/api/v1/admin/collections \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_knowledge_base",
    "display_name": "我的知识库",
    "image_mode": false,
    "embedding_model": "text-embedding-v3",
    "vector_dim": 1536
  }'
```

图文模式知识库：

```bash
curl -X POST http://localhost:8000/api/v1/admin/collections \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_image_kb",
    "display_name": "图文知识库",
    "image_mode": true
  }'
```

---

## 五、上传文件

### 单文件直接上传到知识库

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@/path/to/document.pdf" \
  -F "kb_name=my_knowledge_base" \
  -F "chunk_size=500" \
  -F "chunk_overlap=50"
```

返回：
```json
{
  "success": true,
  "message": "上传任务已提交，后台正在处理，请通过 job_id 查询进度",
  "data": {
    "job_id": "uuid-xxxx",
    "file_id": "uuid-yyyy",
    "file_name": "document.pdf"
  }
}
```

### 查询任务进度

```bash
curl http://localhost:8000/api/v1/jobs/{job_id}
```

状态流转：`pending → chunking → chunked → embedding → done`

### 通过类目批量上传

1. 先上传文件到类目（OSS）：
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload-to-category \
  -F "file=@/path/to/doc.pdf" \
  -F "category_id=uuid-xxxx"
```

2. 触发批量切分到知识库：
```bash
curl -X POST "http://localhost:8000/api/v1/documents/start-chunking/{category_id}?kb_name=my_knowledge_base"
```

---

## 六、RAG 问答

```bash
curl -X POST http://localhost:8000/api/v1/knowledge/ \
  -H "Content-Type: application/json" \
  -d '{
    "query": "你的问题",
    "session_id": "session-001",
    "model": "qwen-plus",
    "collection": "my_knowledge_base"
  }'
```

---

## 七、API 变更说明

### 变更的接口

| 旧接口 | 新接口 | 变更说明 |
|--------|--------|----------|
| `POST /documents/upload` | `POST /documents/upload` | 新增必填参数 `kb_name`，移除 `metadata`/`zh_title_enhance`/`vl_enhance` |
| `POST /documents/start-chunking/{category_id}` | 同左 | `collection` 参数改为 `kb_name`（Query 参数） |
| `POST /jobs/{job_id}/fetch-chunks` | 已删除 | 切分现在自动完成，不需要手动 fetch |
| `POST /jobs/{job_id}/cancel` | 已删除 | 后台任务不支持取消 |
| `GET /jobs` | `GET /jobs?kb_name=xxx` | 新增必填参数 `kb_name` |
| `DELETE /files` | `DELETE /files` | 请求体 `job_id` 改为 `file_id` |
| `POST /files/batch-delete` | 同左 | `job_ids` 改为 `file_ids` |
| `POST /chunks/job/{job_id}/upsert` | 同左 | 逻辑不变，内部改为调 Milvus |
| `GET /admin/config` | 同左 | 返回 Milvus 配置而非 ADB 配置 |
| `GET/POST /admin/collections` | 同左 | 不再需要 namespace/password |
| `GET/DELETE /admin/namespace` | 已删除 | namespace 概念移除 |
| `POST /documents/start-chunking-direct` | 已删除 | 合并进标准上传流程 |

### 新增的接口

| 接口 | 说明 |
|------|------|
| `POST /jobs/{job_id}/upsert` | 手动触发向量化（切片编辑后重新上传 Milvus） |

---

## 八、新表结构

```
knowledge_base          知识库（对应 Milvus collection）
knowledge_category      类目（文件夹，独立体系）
knowledge_category_file 类目文件（OSS 引用）
knowledge_file          知识库文件（kb_id + oss_key）
knowledge_job           处理任务（自维护状态机）
knowledge_chunk         切片当前内容（可编辑）
knowledge_chunk_origin  切片原始内容（只写一次，用于撤回）
knowledge_chunk_image   切片图片（图文模式）
```

主要设计变化：
- `knowledge_upload_file` + `knowledge_document_job` 合并为 `knowledge_file` + `knowledge_job`
- `knowledge_chunk_store` 拆分为 `knowledge_chunk`（当前内容）+ `knowledge_chunk_origin`（原始内容）
- `knowledge_collection_config` 改为 `knowledge_base`，去掉向量技术参数（由 Milvus 管理）
- `namespace_registry` 删除（namespace 概念移除）
- 所有主键改为 UUID（`gen_random_uuid()`），`knowledge_chunk.id` 保持 `{job_id}_{chunk_index}` 格式

---

## 九、常见问题

**Q: Milvus 启动慢，连接超时？**

Milvus 首次启动需要 30-60 秒初始化 etcd 和 MinIO。等待 `docker-compose ps` 显示 healthy 后再启动后端。

**Q: embedding 调用失败？**

检查 `DASHSCOPE_API_KEY` 是否正确，以及网络是否能访问 `dashscope.aliyuncs.com`。

**Q: 切片后 job 状态一直是 chunking？**

查看后端日志，通常是 OSS 下载失败或文件格式不支持。

**Q: 图文模式只支持 PDF 和 DOCX？**

是的，图文模式需要 PyMuPDF 解析图片，目前只支持 `.pdf` 和 `.docx`。标准模式支持 `.pdf`、`.doc`、`.docx`、`.txt`、`.md`、`.ppt`、`.pptx`。

**Q: 前端报 404 on /admin/namespace？**

namespace 接口已删除，前端需要移除对该接口的调用。
