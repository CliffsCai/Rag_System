# 实现计划：文档上传与切片功能优化

## 概述

按照设计文档，分四个模块逐步实现：后端新接口 → 前端 DocList 增强 → 前端 CategoryManager 重构 → 前端 DocUpload 重构，最后串联验证。

## 任务

- [x] 1. 后端：新增文件列表接口
  - [x] 1.1 在 `file_repository.py` 中新增 `list_with_category_name` 方法
    - 通过 JOIN `knowledge_category` 表，在查询结果中附加 `category_name` 字段
    - 支持可选的 `category_id` 过滤参数
    - 支持 `limit` 参数（默认200，最大2000）
    - _需求：4.1、4.2、4.3、4.4、4.6_

  - [ ]* 1.2 为 `list_with_category_name` 编写属性测试
    - **属性 1：文件列表过滤一致性** — 对任意 category_id，返回记录的 category_id 都应匹配
    - **属性 2：文件记录必需字段完整性** — 每条记录包含所有必需字段且关键字段非空
    - **属性 8：limit 参数约束** — 返回数量不超过 limit 值
    - 使用 pytest + hypothesis，最少 100 次迭代
    - _验证：需求 4.2、4.4、4.6_

  - [x] 1.3 新建 `backend/app/api/v1/files.py` 路由文件
    - 实现 `GET /api/v1/files` 端点，接受 `category_id`（可选）和 `limit` 参数
    - 当 `category_id` 不存在时返回 404
    - 调用 `file_repository.list_with_category_name`
    - _需求：4.1、4.2、4.3、4.5_

  - [x] 1.4 在 `backend/app/main.py` 中注册新路由
    - 将 `files.router` 注册到 FastAPI app
    - _需求：4.1_

- [x] 2. 检查点 — 后端接口验证
  - 确保所有测试通过，手动验证 `GET /api/v1/files` 接口可访问，询问用户是否有问题。

- [x] 3. 前端：docApi.js 新增方法
  - [x] 3.1 在 `frontend/src/services/docApi.js` 中新增 `listFiles` 方法
    - `listFiles: (params = {}) => axios.get(\`${BASE}/files\`, { params })`
    - _需求：3.1、3.2、3.3_

- [x] 4. 前端：DocList.vue 增强
  - [x] 4.1 在 `DocList.vue` 顶部新增类目过滤下拉选择器
    - 组件挂载时调用 `docApi.listCategories()` 加载类目选项
    - 选择器支持清空（clearable），清空时展示全量数据
    - _需求：3.1、3.3_

  - [x] 4.2 将 DocList 数据源改为调用 `docApi.listFiles`
    - 默认调用 `listFiles()` 加载全量数据
    - 类目过滤变化时调用 `listFiles({ category_id })` 重新加载
    - _需求：3.2、3.3_

  - [x] 4.3 增强 DocList 表格列和状态渲染
    - 新增"所属类目"列，展示 `category_name`
    - 状态列：queued→info、running→warning、completed→success、failed→danger
    - 操作列：只有 `completed` 状态才显示"查看切片"按钮，其他状态不显示
    - _需求：3.4、3.5、3.6、3.7_

  - [ ]* 4.4 为状态标签映射函数编写属性测试
    - **属性 3：状态标签渲染正确性** — 对任意状态值，标签类型应与状态一一对应
    - 使用 vitest，测试 statusType 函数
    - _验证：需求 3.5、3.6、3.7_

- [x] 5. 前端：CategoryManager.vue 重构
  - [x] 5.1 移除 CategoryManager 中的文件上传功能
    - 删除 `el-upload` 组件及其拖拽区域
    - 删除 `uploadQueue` 响应式状态
    - 删除 `onFileChange` 方法
    - 删除上传进度展示区域
    - _需求：1.1、1.4_

  - [x] 5.2 将类目详情中的文件列表改为只读展示
    - 保留文件列表表格，展示：文件名、切片状态标签、Job ID、上传时间
    - 移除"批量刷新状态"和单行"刷新"操作按钮（简化为只读）
    - _需求：1.3、1.5_

  - [ ]* 5.3 为类目名称校验编写属性测试
    - **属性 4：类目名称验证** — 对任意纯空白字符串，`save` 方法应提前返回不调用 API
    - 使用 vitest，mock docApi，验证空白字符串不触发 API 调用
    - _验证：需求 1.6_

- [x] 6. 前端：DocUpload.vue 重构
  - [x] 6.1 修改页面标题和说明文字
    - 卡片标题改为"选择类目并切片"
    - 说明文字更新为：选择类目后上传文件，文件将关联到所选类目并自动提交切片任务
    - _需求：2.1_

  - [x] 6.2 新增"选择类目后展示文件历史"功能
    - 监听 `selectedCategoryId` 变化，变化时调用 `docApi.getCategory(id)` 加载文件历史
    - 在上传区下方新增文件历史列表（el-table），展示：文件名、状态标签、Job ID、上传时间
    - 上传成功后调用同一方法刷新文件历史列表
    - _需求：2.3、2.6_

  - [x] 6.3 确保上传区在未选类目时禁用
    - `el-upload` 的 `disabled` 属性绑定 `!selectedCategoryId`
    - `beforeUpload` 中二次校验 `selectedCategoryId`，为空时返回 false 并提示
    - _需求：2.4、2.11_

  - [ ]* 6.4 为文件格式校验函数编写属性测试
    - **属性 7：文件格式验证** — 对任意不在允许列表中的扩展名，`beforeUpload` 应返回 false
    - 使用 vitest，测试 `beforeUpload` 函数
    - _验证：需求 2.8_

  - [ ]* 6.5 为上传参数透传编写属性测试
    - **属性 6：上传参数透传完整性** — 对任意合法参数组合，uploadData computed 的值应与 config 一致
    - 使用 vitest，验证 uploadData 计算属性
    - _验证：需求 2.5、2.10_

- [x] 7. 检查点 — 前端功能验证
  - 确保所有测试通过，询问用户是否有问题。

- [ ] 8. 后端：含文件类目删除保护属性测试
  - [ ]* 8.1 为 `DELETE /categories/{id}` 编写属性测试
    - **属性 5：含文件类目删除保护** — 对任意含有文件的类目，删除请求应返回 400
    - 使用 pytest + hypothesis，生成随机数量的文件记录
    - _验证：需求 1.7_

- [x] 9. 最终检查点
  - 确保所有测试通过，整体功能串联验证，询问用户是否有问题。

## 备注

- 标有 `*` 的子任务为可选测试任务，可跳过以加快 MVP 交付
- 每个属性测试引用设计文档中对应的属性编号
- 后端属性测试使用 pytest + hypothesis（最少 100 次迭代）
- 前端属性测试使用 vitest（如需属性测试可引入 fast-check）
