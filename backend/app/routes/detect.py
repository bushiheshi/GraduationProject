from fastapi import APIRouter, Depends, HTTPException, status

from app.code_detection_service import (
    CodeDetectionConfigurationError,
    CodeDetectionUnavailableError,
    detect_code_authorship,
)
from app.dependencies import get_current_user
from app.models import UserRole
from app.schemas import CodeDetectionRequest, CodeDetectionResponse

router = APIRouter(prefix='/api/detect', tags=['detect'])


@router.post('/code', response_model=CodeDetectionResponse)
def detect_code(
    payload: CodeDetectionRequest,
    current_user=Depends(get_current_user),
):
    # 作业判别接口默认只开放给教师，避免学生直接拿同一个检测器反向试探阈值。
    if current_user.role != UserRole.TEACHER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only teachers can detect AI-generated code')

    try:
        result = detect_code_authorship(
            code=payload.code,
            filename=payload.filename,
            language=payload.language,
        )
    except CodeDetectionConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except CodeDetectionUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return CodeDetectionResponse(**result)
