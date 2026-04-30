# 当前项目状态

最后更新：2026-04-30

这份文档用于后续开发交接，记录当前项目已经完成的产品形态、关键约束和常用验证方式。

## 产品形态

Book-Grounded Learning Agent 是一个网页端 AI 读书学习教练。用户导入服务器本地 PDF 后，系统会保存书籍、页码、章节、文本切片和学习进程，并通过 `/app` 提供可继续学习、可复习、可随时提问的界面。

当前只维护 Web UI 加 FastAPI 后端。旧的 CLI 学习流程已经移除，后续新功能应优先接入网页端。

## 当前能力

- 从服务器本地 PDF 路径导入书籍。
- 使用 SQLite 保存 books、sections、chunks、plans、sessions、messages、app_settings 和 lesson_outputs。
- 支持 `programming` 与 `humanities` 两种学习模式。
- 使用页码窗口生成学习计划，不再提前固定整本书所有课程。
- 用户可以在学习过程中调整后续每课页数。
- 模型可以通过 `[[NEXT_PAGE_WINDOW: N]]` 建议后续阅读页数，后端会移除该控制标记并重建未来课程。
- 主线课程内容保存到 `lesson_outputs`。
- 随时提问显示在独立问答区，不覆盖主线课程内容。
- 上一课、下一课会优先加载已经保存的课程内容。
- 网页端可以配置 API Key、Base URL、模型名、reasoning effort 和 thinking type。

## 大模型调用策略

运行时已经移除本地 fallback 学习内容。

如果没有配置 API Key、Base URL 或模型调用失败，后端会返回 `reply_kind = "error"` 的 `TutorReply`，并且不会保存课程输出。这是有意设计：项目不应在模型不可用时生成看似真实的学习内容。

常见失败原因：

- 网页端没有保存 API Key。
- Base URL 填错或为空。
- 模型名不是当前服务商支持的模型。
- reasoning 或 thinking 参数不被当前服务商接受。
- 服务重启后使用了不同的数据目录或数据库。

## 常用启动方式

```powershell
python -m book_agent.main --port 8001
```

或使用 Conda：

```powershell
conda run --no-capture-output -n test1 python -m book_agent.main --port 8001
```

常用地址：

- Web App: `http://127.0.0.1:8001/app`
- API Docs: `http://127.0.0.1:8001/docs`
- Health Check: `http://127.0.0.1:8001/health`

## 关键文件

- `book_agent/main.py`：FastAPI 应用、静态前端和 API 路由。
- `book_agent/tutor.py`：课程推进、prompt 组装、大模型调用、课程输出保存。
- `book_agent/db.py`：SQLite schema 和迁移。
- `book_agent/learning_process.py`：导入书籍并创建学习进程。
- `book_agent/planner.py`：页码窗口课程计划和未来课程重建。
- `book_agent/retrieval.py`：当前课程相关文本检索。
- `book_agent/llm_settings.py`：网页端保存的大模型配置。
- `book_agent/learning_modes/`：两种学习模式的 prompt 模板。
- `book_agent/web/index.html`：前端页面结构。
- `book_agent/web/app.js`：前端状态、课程翻页、问答显示和 API 调用。
- `book_agent/web/styles.css`：前端样式。
- `tests/`：回归测试。

## API 概览

- `GET /app`
- `GET /health`
- `GET /settings/llm`
- `PATCH /settings/llm`
- `POST /books/import`
- `GET /books`
- `GET /books/{book_id}`
- `POST /plans/generate`
- `GET /plans/{plan_id}`
- `POST /sessions`
- `GET /sessions`
- `GET /sessions/{session_id}`
- `DELETE /sessions/{session_id}`
- `DELETE /sessions`
- `POST /sessions/{session_id}/messages`
- `GET /sessions/{session_id}/lessons/{lesson_number}/output`
- `PATCH /sessions/{session_id}/learning-mode`
- `PATCH /sessions/{session_id}/page-window`
- `POST /sessions/{session_id}/advance`
- `POST /sessions/{session_id}/retreat`

## 验证命令

```powershell
python -m pytest -q
node --check book_agent\web\app.js
```

## 后续适合开发的方向

1. 支持浏览器直接上传 PDF，而不是填写服务器本地路径。
2. 增加大模型流式输出。
3. 为每个学习进程保存独立模型配置。
4. 增加课程地图，显示已生成、未生成、已复习状态。
5. 改进 Markdown 渲染和代码高亮。
6. 增加笔记、练习完成记录和复习计划。
