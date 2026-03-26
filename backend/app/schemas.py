from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole


class UserRegisterRequest(BaseModel):
    account: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    role: UserRole
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    account: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: UserRole | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account: str
    name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class ApiMessage(BaseModel):
    message: str


class ChatModelInfo(BaseModel):
    key: str
    provider: str
    model_name: str


class ChatConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ChatConversationResponse(BaseModel):
    id: int
    title: str
    updated_at: datetime
    last_generated_at: datetime | None = None
    record_count: int
    submission_count: int = 0
    last_submitted_at: datetime | None = None


class ChatCompletionRequest(BaseModel):
    model: str = Field(min_length=1, max_length=32)
    prompt: str = Field(min_length=1, max_length=8000)
    conversation_id: int | None = None


class ChatRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int | None
    model_name: str
    generated_at: datetime
    prompt: str
    content: str
    citations: list[str]


class ChatCompletionResponse(ChatRecordResponse):
    conversation_title: str


class HomeworkSubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    conversation_title: str
    model_name: str
    prompt: str
    content: str
    citations: list[str]
    source_generated_at: datetime
    submitted_at: datetime


class CodeDetectionRequest(BaseModel):
    # 这里只接收单份代码文本；文件名和语言只用于回显与日志，不参与强依赖判断。
    code: str = Field(min_length=1, max_length=200000)
    filename: str | None = Field(default=None, max_length=255)
    language: str | None = Field(default=None, max_length=64)


class CodeChunkScore(BaseModel):
    chunk_index: int
    start_offset: int
    end_offset: int
    machine_generated_probability: float
    human_generated_probability: float


class CodeDetectionResponse(BaseModel):
    model_id: str
    filename: str | None = None
    language: str | None = None
    label: str
    confidence: float
    threshold: float
    machine_generated_probability: float
    human_generated_probability: float
    code_length: int
    chunk_count: int
    explanation: str
    chunk_scores: list[CodeChunkScore]
