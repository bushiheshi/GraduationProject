# Backend (Login + Chat + MySQL + Vue3 Frontend)

## 1. Prepare

1. Copy env file:

```powershell
Copy-Item backend/.env.example backend/.env
```

2. Edit `backend/.env` and set your MySQL + model API keys:

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DB=aigc_platform

QWEN_API_KEY=your_qwen_key
QWEN_BASE_URL=https://dashscope.aliyuncs.com
QWEN_MODEL=qwen-coder-turbo-0919

DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

CHAT_TIMEOUT_SECONDS=90
CHAT_CONVERSATION_TURN_LIMIT=5

CODE_DETECT_MODEL_ID=project-droid/DroidDetect-Large-Binary
CODE_DETECT_THRESHOLD=0.6
CODE_DETECT_CHUNK_CHARS=6000
CODE_DETECT_CHUNK_OVERLAP_CHARS=800
CODE_DETECT_MAX_LENGTH=2048
```

3. Install dependencies:

```powershell
pip install -r backend/requirements.txt
```

4. Initialize database and tables:

```powershell
cd backend
python scripts/init_db.py
```

5. Run API (from `backend` directory):

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 2. Frontend (Vue3)

- Vue3 frontend source is in `frontend/`.
- Login page: `http://127.0.0.1:8000/` (served from `frontend/login.html`)
- Student page: `http://127.0.0.1:8000/frontend/student.html`
- After student login success, it automatically redirects to student page.

## 3. APIs

### Auth

- `POST /api/auth/register`
- `POST /api/auth/login` (generic)
- `POST /api/auth/login/student`
- `POST /api/auth/login/teacher`
- `GET /api/auth/me`

### Chat (student only)

- `GET /api/chat/models` 获取可选模型
- `GET /api/chat/conversations` 获取当前学生的对话列表
- `POST /api/chat/conversations` 新建一条对话
- `GET /api/chat/conversations/{conversation_id}/records` 获取某条对话当前保留的问答记录
- `POST /api/chat/completions` 在指定对话中继续发起对话并落库
- `POST /api/chat/conversations/{conversation_id}/submissions` 将当前对话最近一轮问答作为最终作业提交并落库

说明：
- 系统会按对话维度保存上下文。
- 每条对话最多保留最近 `5` 轮问答，超过后会自动移除最早记录，避免 token 消耗过高。
- 再次点击左侧某条对话继续发送时，会自动带上该对话最近的上下文。

`POST /api/chat/completions` 请求体示例：

```json
{
  "model": "qwen",
  "conversation_id": 12,
  "prompt": "继续上一题，给我一个更生活化的例子"
}
```

响应与数据库会记录以下字段：
- 对话 ID（`conversation_id`）
- 对话标题（`conversation_title`，首次发送后会根据问题自动生成）
- 模型名称（`model_name`）
- 生成时间（`generated_at`）
- 引用文献或资料（`citations`）
- 生成内容（`content`）
- 学生提示词（`prompt`）

最终作业提交说明：
- 学生点击学生页中的“提交最终作业”按钮后，系统会把当前对话最近一轮问答快照保存到 `homework_submissions` 表。
- 提交记录会额外保存提交时间（`submitted_at`），即使后续对话继续进行或旧聊天记录被裁剪，已提交的作业快照仍会保留。

### Code Detection (teacher only)

- `POST /api/detect/code` 检测一段代码更偏向人工编写还是 AI 生成

说明：
- 当前接口默认只允许教师账号调用。
- 后端默认使用 `project-droid/DroidDetect-Large-Binary`。
- 长代码会自动切片后分别打分，再按片段长度做加权平均。
- 返回结果包含总分、阈值、结论，以及每个代码分片的独立分数，便于后续做教师端展示。

请求体示例：

```json
{
  "filename": "homework.py",
  "language": "python",
  "code": "def hello():\n    print('hello world')"
}
```

## 4. Other

- `GET /health`
