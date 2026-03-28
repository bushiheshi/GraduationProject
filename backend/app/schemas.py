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
    assignment_id: int | None = None
    assignment_description: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = Field(min_length=1, max_length=32)
    prompt: str = Field(min_length=1, max_length=8000)
    conversation_id: int | None = None


class AnswerSubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    answer_text: str
    source_filename: str | None = None
    created_at: datetime
    updated_at: datetime


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


class AssignmentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)


class TeacherAssignmentResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    student_count: int
    submitted_count: int


class TeacherAssignmentSubmissionResponse(BaseModel):
    student_id: int
    student_account: str
    student_name: str
    conversation_id: int
    has_submission: bool
    submitted_at: datetime | None = None
    source_filename: str | None = None
    answer_preview: str | None = None


class TeacherAssignmentSubmissionDetailResponse(BaseModel):
    student_id: int
    student_account: str
    student_name: str
    conversation_id: int
    has_submission: bool
    submitted_at: datetime | None = None
    source_filename: str | None = None
    answer_text: str | None = None

