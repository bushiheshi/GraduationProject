from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.bootstrap import init_app_database, ping_database
from app.config import get_settings
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent.parent
STATIC_DIR = BASE_DIR / 'static'
FRONTEND_DIR = PROJECT_DIR / 'frontend'


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 启动时先验证数据库连通，再执行建表和演示数据初始化。
    ping_database()
    init_app_database(seed_demo_users=True)
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.include_router(auth_router)
app.include_router(chat_router)
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
app.mount('/frontend', StaticFiles(directory=FRONTEND_DIR), name='frontend')


@app.get('/health')
def health_check():
    return {'status': 'ok'}


@app.get('/')
def login_page():
    return RedirectResponse(url='/frontend/login.html', status_code=302)
