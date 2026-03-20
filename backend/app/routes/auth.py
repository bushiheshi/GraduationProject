from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.crud import create_user, get_user_by_account
from app.dependencies import get_current_user, get_db
from app.models import UserRole
from app.schemas import LoginRequest, TokenResponse, UserRegisterRequest, UserResponse
from app.security import create_access_token, get_password_hash, verify_password

router = APIRouter(prefix='/api/auth', tags=['auth'])


def _issue_token(payload: LoginRequest, db: Session, required_role: UserRole | None = None) -> TokenResponse:
    user = get_user_by_account(db, payload.account)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid account or password')

    # Caller can lock role by endpoint, while generic endpoint can still pass role in payload.
    expected_role = required_role or payload.role
    if expected_role and user.role != expected_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Role mismatch')

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='User is inactive')

    token = create_access_token(subject=user.account, role=user.role.value)
    return TokenResponse(access_token=token)


@router.post('/register', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    exists = get_user_by_account(db, payload.account)
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Account already exists')

    user = create_user(
        db=db,
        account=payload.account,
        name=payload.name,
        role=payload.role,
        password_hash=get_password_hash(payload.password),
    )
    return user


@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return _issue_token(payload, db)


@router.post('/login/student', response_model=TokenResponse)
def student_login(payload: LoginRequest, db: Session = Depends(get_db)):
    return _issue_token(payload, db, required_role=UserRole.STUDENT)


@router.post('/login/teacher', response_model=TokenResponse)
def teacher_login(payload: LoginRequest, db: Session = Depends(get_db)):
    return _issue_token(payload, db, required_role=UserRole.TEACHER)


@router.get('/me', response_model=UserResponse)
def me(current_user=Depends(get_current_user)):
    return current_user
