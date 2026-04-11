from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.crud import (
    create_assignment_with_conversations,
    get_assignment_keyword_detail,
    get_assignment_submission_detail,
    list_assignment_question_keywords,
    list_assignment_submissions,
    list_assignments_by_teacher,
)
from app.dependencies import get_current_user, get_db
from app.models import UserRole
from app.schemas import (
    AssignmentCreateRequest,
    TeacherAssignmentResponse,
    TeacherAssignmentKeywordDetailResponse,
    TeacherAssignmentKeywordResponse,
    TeacherAssignmentSubmissionDetailResponse,
    TeacherAssignmentSubmissionResponse,
)

router = APIRouter(prefix='/api/teacher', tags=['teacher'])


@router.get('/assignments', response_model=list[TeacherAssignmentResponse])
def get_assignments(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    _require_teacher(current_user)
    assignments = list_assignments_by_teacher(db, teacher_id=current_user.id)
    return [_to_assignment_response(item) for item in assignments]


@router.post('/assignments', response_model=TeacherAssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_teacher(current_user)

    normalized_title = payload.title.strip()
    if not normalized_title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Assignment title is required')

    assignment_data = create_assignment_with_conversations(
        db,
        teacher_id=current_user.id,
        title=normalized_title,
        description=payload.description,
    )
    return _to_assignment_response(assignment_data)


@router.get(
    '/assignments/{assignment_id}/submissions',
    response_model=list[TeacherAssignmentSubmissionResponse],
)
def get_assignment_submissions(
    assignment_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_teacher(current_user)
    result = list_assignment_submissions(db, assignment_id=assignment_id, teacher_id=current_user.id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assignment not found')
    return [TeacherAssignmentSubmissionResponse(**item) for item in result['submissions']]


@router.get(
    '/assignments/{assignment_id}/question-keywords',
    response_model=list[TeacherAssignmentKeywordResponse],
)
def get_assignment_question_keywords(
    assignment_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_teacher(current_user)
    result = list_assignment_question_keywords(db, assignment_id=assignment_id, teacher_id=current_user.id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assignment not found')
    return [TeacherAssignmentKeywordResponse(**item) for item in result['keywords']]


@router.get(
    '/assignments/{assignment_id}/question-keywords/detail',
    response_model=TeacherAssignmentKeywordDetailResponse,
)
def get_assignment_question_keyword_detail(
    assignment_id: int,
    keyword: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_teacher(current_user)
    result = get_assignment_keyword_detail(
        db,
        assignment_id=assignment_id,
        teacher_id=current_user.id,
        keyword=keyword,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assignment not found')
    return TeacherAssignmentKeywordDetailResponse(**result)


@router.get(
    '/assignments/{assignment_id}/submissions/{student_id}',
    response_model=TeacherAssignmentSubmissionDetailResponse,
)
def get_submission_detail(
    assignment_id: int,
    student_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_teacher(current_user)
    result = get_assignment_submission_detail(
        db,
        assignment_id=assignment_id,
        teacher_id=current_user.id,
        student_id=student_id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Submission not found')
    return TeacherAssignmentSubmissionDetailResponse(**result['submission'])


def _require_teacher(current_user) -> None:
    if current_user.role != UserRole.TEACHER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only teachers can access this page')


def _to_assignment_response(item: dict) -> TeacherAssignmentResponse:
    assignment = item['assignment']
    return TeacherAssignmentResponse(
        id=assignment.id,
        title=assignment.title,
        description=assignment.description,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
        student_count=int(item.get('student_count') or 0),
        submitted_count=int(item.get('submitted_count') or 0),
    )
