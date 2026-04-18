from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.crud import (
    create_assignment_with_conversations,
    get_assignment_keyword_detail,
    get_assignment_submission_detail,
    get_teacher_question_overview,
    list_assignment_answer_texts_for_assessment,
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
    TeacherAssessmentLowScoreStudentResponse,
    TeacherAssessmentRiskFlagStatResponse,
    TeacherAssessmentSummaryResponse,
    TeacherSubmissionAssessmentResponse,
    TeacherQuestionOverviewResponse,
)
from app.services.answer_assessment import (
    AssessmentResourceError,
    assess_answer_credibility,
    build_student_assessment_summary,
    build_teacher_report,
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


@router.get('/question-overview', response_model=TeacherQuestionOverviewResponse)
def get_question_overview(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    _require_teacher(current_user)
    overview = get_teacher_question_overview(db, teacher_id=current_user.id)
    return TeacherQuestionOverviewResponse(**overview)


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
    '/assignments/{assignment_id}/assessment-summary',
    response_model=TeacherAssessmentSummaryResponse,
)
def get_assignment_assessment_summary(
    assignment_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_teacher(current_user)
    result = list_assignment_answer_texts_for_assessment(
        db,
        assignment_id=assignment_id,
        teacher_id=current_user.id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assignment not found')

    assignment = result['assignment']
    question_text = _build_assignment_question_text(assignment)
    rows = result['submissions']
    if not rows:
        return TeacherAssessmentSummaryResponse(
            assignment_id=assignment_id,
            submitted_count=0,
            assessed_count=0,
        )

    assessed_items = []
    for row in rows:
        try:
            assessment = assess_answer_credibility(
                answer_text=row['answer_text'],
                question_text=question_text,
                ai_source='not_provided',
            )
        except ValueError:
            continue
        except AssessmentResourceError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

        student_summary = build_student_assessment_summary(assessment)
        assessed_items.append(
            {
                'student_id': row['student_id'],
                'student_account': row['student_account'],
                'student_name': row['student_name'],
                'score': float(assessment['score']),
                'label': assessment['label'],
                'risk_flags': assessment.get('risk_flags') or [],
                'main_shortcomings': student_summary.get('main_shortcomings') or [],
            }
        )

    scores = [item['score'] for item in assessed_items]
    if not scores:
        return TeacherAssessmentSummaryResponse(
            assignment_id=assignment_id,
            submitted_count=len(rows),
            assessed_count=0,
        )

    level_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for item in assessed_items:
        level_counts[item['label']] = level_counts.get(item['label'], 0) + 1
        for flag in item['risk_flags']:
            risk_counts[flag] = risk_counts.get(flag, 0) + 1

    pass_count = sum(1 for score in scores if score >= 60)
    low_score_items = sorted(assessed_items, key=lambda item: item['score'])[:5]

    return TeacherAssessmentSummaryResponse(
        assignment_id=assignment_id,
        submitted_count=len(rows),
        assessed_count=len(assessed_items),
        average_score=round(sum(scores) / len(scores), 2),
        highest_score=round(max(scores), 2),
        lowest_score=round(min(scores), 2),
        pass_count=pass_count,
        pass_rate=round(pass_count / len(scores) * 100),
        at_risk_count=sum(1 for item in assessed_items if item['score'] < 60 or item['label'] in {'存疑', '低可信'}),
        level_counts=level_counts,
        risk_flag_counts=[
            TeacherAssessmentRiskFlagStatResponse(flag=flag, count=count)
            for flag, count in sorted(risk_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
        ],
        low_score_students=[
            TeacherAssessmentLowScoreStudentResponse(
                student_id=item['student_id'],
                student_account=item['student_account'],
                student_name=item['student_name'],
                score=item['score'],
                label=item['label'],
                main_shortcomings=item['main_shortcomings'],
            )
            for item in low_score_items
        ],
    )


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

    submission = result['submission']
    assignment = result['assignment']
    assessment_report = None
    if submission.get('has_submission') and submission.get('answer_text'):
        question_text = _build_assignment_question_text(assignment)
        try:
            assessment_result = assess_answer_credibility(
                answer_text=submission['answer_text'],
                question_text=question_text,
                ai_source='not_provided',
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except AssessmentResourceError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        assessment_result['report_markdown'] = build_teacher_report(
            result=assessment_result,
            answer_text=submission['answer_text'],
            question_text=question_text,
        )
        assessment_report = TeacherSubmissionAssessmentResponse(**assessment_result)

    return TeacherAssignmentSubmissionDetailResponse(**submission, assessment_report=assessment_report)


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


def _build_assignment_question_text(assignment) -> str | None:
    parts = [assignment.title, assignment.description]
    return '\n'.join(part.strip() for part in parts if part and part.strip()) or None
