# 需求文档：文档上传与切片功能优化

## 简介

本次优化针对知识库管理系统中文档上传和切片功能的职责混乱问题，采用方案B进行重构。

**方案B核心原则**：由于系统没有独立的文件存储服务，文件内容无法在上传后持久化到本地磁盘，因此：
- 类目管理页面**只负责类目的增删改查**，不包含文件上传功能
- "选择类目并切片"页面支持两种操作：
  1. 拖入新文件 → 选类目 → 切片（一步完成，同时记录到 file 表）
  2. 查看该类目下已切片的文件历史
- 文件列表页面增加按类目过滤和状态展示

## 词汇表

- **CategoryManager（类目管理器）**：负责类目增删改查的前端组件
- **DocUpload（文档上传切片）**：重构后的"选择类目并切片"前端组件
- **DocList（文件列表）**：展示切片任务历史的前端组件
- **File（文件记录）**：`knowledge_upload_file` 表中的一条记录，关联类目和 Job
- **Job（切片任务）**：`knowledge_job` 表中的一条记录，代表一次切片任务
- **切片（Slice）**：将文档内容按配置参数分割成小块的过程，通过 ADBDocumentService 执行
- **类目（Category）**：`knowledge_category` 表中的一条记录，用于组织文件

---

## 需求

### 需求 1：类目管理重构（移除上传功能）

**用户故事：** 作为知识库管理员，我希望类目管理页面只负责类目的增删改查，不包含文件上传功能，以便职责清晰、界面简洁。

#### 验收标准

1. THE CategoryManager SHALL 只提供类目的创建、查看、编辑、删除功能
2. WHEN 用户进入类目管理页面，THE CategoryManager SHALL 展示类目列表，包含类目名称、描述、文件数量和创建时间
3. WHEN 用户点击某个类目，THE CategoryManager SHALL 展示该类目的详情，包含类目名称、描述和该类目下的文件历史列表
4. THE CategoryManager SHALL 不包含任何文件上传区域或上传触发逻辑
5. WHEN 用户在类目详情页查看文件列表，THE CategoryManager SHALL 展示每个文件的文件名、切片状态（queued/running/completed/failed）、关联的 Job ID 和上传时间
6. WHEN 用户新建类目时输入空名称，THE CategoryManager SHALL 阻止提交并提示"请输入类目名称"
7. WHEN 用户删除含有文件的类目，THE CategoryManager SHALL 拒绝删除并提示"类目下还有 N 个文件，请先删除文件"
8. WHEN 用户成功创建类目，THE CategoryManager SHALL 刷新类目列表并显示新建的类目

### 需求 2：选择类目并切片（重构 DocUpload）

**用户故事：** 作为知识库管理员，我希望在一个页面内完成"选择类目 + 上传文件 + 配置切片参数 + 提交切片"的完整流程，并能查看该类目下的历史切片记录，以便高效管理文档。

#### 验收标准

1. THE DocUpload SHALL 将页面标题改为"选择类目并切片"
2. WHEN 用户打开 DocUpload 页面，THE DocUpload SHALL 展示类目下拉选择器、切片参数配置区和文件拖拽上传区
3. WHEN 用户选择一个类目，THE DocUpload SHALL 在页面下方展示该类目下已有的文件历史列表（从 `/api/v1/categories/{id}` 获取）
4. WHEN 用户选择一个类目，THE DocUpload SHALL 激活文件上传区域（未选类目时上传区域禁用）
5. WHEN 用户拖入或选择文件并点击上传，THE DocUpload SHALL 调用 `POST /api/v1/documents/upload` 接口，同时传入 category_id 和切片参数
6. WHEN 文件上传成功，THE DocUpload SHALL 显示成功提示，并刷新该类目下的文件历史列表
7. WHEN 文件上传成功，THE DocUpload SHALL 提供"查看任务列表"的跳转入口
8. WHEN 用户上传不支持格式的文件（非 PDF/Word/PPT/TXT/MD），THE DocUpload SHALL 阻止上传并提示不支持的格式
9. WHEN 用户上传超过 200MB 的文件，THE DocUpload SHALL 阻止上传并提示文件超限
10. THE DocUpload SHALL 支持配置切片参数：chunk_size（100-2048，默认800）、chunk_overlap（0-chunk_size，默认100）、zh_title_enhance（默认开启）、vl_enhance（默认关闭）
11. WHEN 用户未选择类目时尝试上传，THE DocUpload SHALL 阻止上传并提示"请先选择类目"

### 需求 3：文件列表增强

**用户故事：** 作为知识库管理员，我希望在文件列表中能按类目过滤，并清晰看到每个文件的切片状态，以便快速定位和管理文件。

#### 验收标准

1. THE DocList SHALL 在列表顶部提供按类目过滤的下拉选择器
2. WHEN 用户选择一个类目进行过滤，THE DocList SHALL 只展示该类目下的文件记录
3. WHEN 用户清空类目过滤，THE DocList SHALL 展示所有文件记录
4. THE DocList SHALL 展示每条记录的文件名、所属类目名称、Job ID、切片状态和上传时间
5. WHEN 文件的切片状态为 completed，THE DocList SHALL 在该行显示"查看切片"操作按钮
6. WHEN 文件的切片状态为 queued 或 running，THE DocList SHALL 显示对应的状态标签（排队中/处理中）
7. WHEN 文件的切片状态为 failed，THE DocList SHALL 以红色标签显示"失败"状态
8. THE DocList SHALL 支持手动刷新列表

### 需求 4：后端 API 增强（文件列表接口）

**用户故事：** 作为前端开发者，我希望后端提供支持按类目过滤的文件列表接口，以便文件列表页面能高效查询。

#### 验收标准

1. THE FileListAPI SHALL 提供 `GET /api/v1/files` 接口，返回文件记录列表
2. WHEN 请求携带 `category_id` 查询参数，THE FileListAPI SHALL 只返回该类目下的文件记录
3. WHEN 请求不携带 `category_id` 参数，THE FileListAPI SHALL 返回所有文件记录
4. THE FileListAPI SHALL 在每条文件记录中包含 file_id、category_id、category_name、file_name、job_id、status、error、created_at 字段
5. IF 指定的 category_id 不存在，THEN THE FileListAPI SHALL 返回 404 错误和描述信息
6. THE FileListAPI SHALL 支持 `limit` 参数（默认200，最大2000）控制返回数量
