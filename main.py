import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------- 1. 加载环境变量 ----------
load_dotenv()
os.environ.setdefault('HOME', '/tmp')

# ---------- 2. 日志配置 ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- 3. 导入路由 ----------
from app.api.v1.router import router as v1_router


# ---------- 4. 生命周期 ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('应用启动中...')
    # 打印已注册路由（调试用）
    print('\n=== 已注册的路由 ===')
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f'  {route.path} -> {route.methods}')
    print('===================\n')
    yield
    logger.info('应用关闭中...')


# ---------- 5. 创建应用 ----------
def create_app() -> FastAPI:
    app = FastAPI(
        title='AIhub-Afdian',
        description='爱发电 Webhook 自动生成 New API 兑换码',
        version='1.0.0',
        lifespan=lifespan,
        redirect_slashes=False,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_methods=['GET', 'POST', 'OPTIONS'],
        allow_headers=['*'],
    )

    # 注册 v1 路由
    app.include_router(v1_router, prefix='/api/v1')

    # 全局异常处理器
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f'全局异常: {exc}', exc_info=True)
        return JSONResponse(
            status_code=500,
            content={'code': 500, 'msg': f'服务器内部错误: {str(exc)}'},
        )

    # 健康检查
    @app.get('/health', tags=['系统'])
    async def health_check():
        return {'status': 'ok', 'version': '1.0.0'}

    @app.get('/', tags=['系统'])
    async def root():
        return {
            'message': 'API 服务已启动',
            'health': '/health',
            'docs': '/docs',
        }

    return app


# ---------- 6. 导出实例 ----------
app = create_app()

# ---------- 7. 直接运行 ----------
if __name__ == '__main__':
    import uvicorn

    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)
