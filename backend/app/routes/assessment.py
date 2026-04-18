from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.models import UserRole
from app.schemas import AssessmentCredibilityRequest, AssessmentCredibilityResponse
from app.services.answer_assessment import (
    AssessmentResourceError,
    assess_answer_credibility,
    build_teacher_report,
)

router = APIRouter(prefix='/api/assessment', tags=['assessment'])


@router.post('/credibility', response_model=AssessmentCredibilityResponse)
def assess_credibility(payload: AssessmentCredibilityRequest, current_user=Depends(get_current_user)):
    if current_user.role != UserRole.TEACHER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only teachers can assess submissions')

    try:
        result = assess_answer_credibility(
            answer_text=payload.answer_text,
            question_text=payload.question_text,
            chapter=payload.chapter,
            section=payload.section,
            max_order=payload.max_order,
            semantic_top_k=payload.semantic_top_k,
            report_top_k=payload.report_top_k,
            ai_rate=payload.ai_rate,
            ai_source=payload.ai_source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AssessmentResourceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if payload.include_report:
        result['report_markdown'] = build_teacher_report(
            result=result,
            answer_text=payload.answer_text,
            question_text=payload.question_text,
        )
    else:
        result['report_markdown'] = None

    return AssessmentCredibilityResponse(**result)
