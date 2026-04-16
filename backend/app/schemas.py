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


class TeacherAiUsageModelStatResponse(BaseModel):
    model_name: str
    count: int


class TeacherAiUsageStageStatResponse(BaseModel):
    key: str
    label: str
    count: int


class TeacherAiUsageTimelineItemResponse(BaseModel):
    record_id: int
    generated_at: datetime
    model_name: str
    stage_label: str
    prompt_preview: str


class TeacherAiUsageSummaryResponse(BaseModel):
    total_count: int = 0
    first_used_at: datetime | None = None
    last_used_at: datetime | None = None
    pre_submission_count: int = 0
    post_submission_count: int = 0
    models_used: list[str] = Field(default_factory=list)
    model_stats: list[TeacherAiUsageModelStatResponse] = Field(default_factory=list)
    stage_stats: list[TeacherAiUsageStageStatResponse] = Field(default_factory=list)
    behavior_tags: list[str] = Field(default_factory=list)
    learning_summary: str = '未检测到该作业的 AI 使用记录。'
    timeline: list[TeacherAiUsageTimelineItemResponse] = Field(default_factory=list)


class TeacherAssignmentKeywordResponse(BaseModel):
    keyword: str
    count: int
    student_count: int
    sample_prompts: list[str] = Field(default_factory=list)
    sample_students: list[str] = Field(default_factory=list)


class TeacherQuestionStudentStatResponse(BaseModel):
    student_id: int
    student_account: str
    student_name: str
    question_count: int
    assignment_count: int
    last_asked_at: datetime | None = None


class TeacherQuestionOverviewResponse(BaseModel):
    total_question_count: int
    student_count: int
    keyword_count: int
    total_keyword_hits: int
    keywords: list[TeacherAssignmentKeywordResponse] = Field(default_factory=list)
    students: list[TeacherQuestionStudentStatResponse] = Field(default_factory=list)


class TeacherAssignmentKeywordMatchResponse(BaseModel):
    record_id: int
    conversation_id: int
    student_id: int
    student_account: str
    student_name: str
    generated_at: datetime
    prompt: str
    content: str
    submitted_at: datetime | None = None
    submission_answer_preview: str | None = None


class TeacherAssignmentKeywordDetailResponse(BaseModel):
    keyword: str
    count: int
    student_count: int
    matches: list[TeacherAssignmentKeywordMatchResponse] = Field(default_factory=list)


class TeacherAssignmentSubmissionResponse(BaseModel):
    student_id: int
    student_account: str
    student_name: str
    conversation_id: int
    has_submission: bool
    submitted_at: datetime | None = None
    source_filename: str | None = None
    answer_preview: str | None = None
    ai_usage_count: int = 0
    ai_models_used: list[str] = Field(default_factory=list)
    ai_last_used_at: datetime | None = None
    ai_learning_summary: str | None = None


class TeacherAssignmentSubmissionDetailResponse(BaseModel):
    student_id: int
    student_account: str
    student_name: str
    conversation_id: int
    has_submission: bool
    submitted_at: datetime | None = None
    source_filename: str | None = None
    answer_text: str | None = None
    ai_usage: TeacherAiUsageSummaryResponse = Field(default_factory=TeacherAiUsageSummaryResponse)
