import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.bootstrap import init_app_database, ping_database
from app.config import get_settings
from app.routes.assessment import router as assessment_router
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.teacher import router as teacher_router

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent.parent
STATIC_DIR = BASE_DIR / 'static'
FRONTEND_DIR = PROJECT_DIR / 'frontend'

mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('text/css', '.css')


@asynccontextmanager
async def lifespan(_: FastAPI):
    ping_database()
    init_app_database(seed_demo_users=True)
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(teacher_router)
app.include_router(assessment_router)
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
app.mount('/frontend', StaticFiles(directory=FRONTEND_DIR), name='frontend')


@app.get('/health')
def health_check():
    return {'status': 'ok'}


@app.get('/')
def login_page():
    return RedirectResponse(url='/frontend/login.html', status_code=302)
