import os
import logging
from contextlib import asynccontextmanager

# 不再在顶层加载 .env
# 在直接运行时加载

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('应用启动中...')
    print('\n=== 应用启动时已注册路由 ===')
    for route in app.routes:
        if hasattr(route, 'path'):
            print(f'  {route.path} -> {getattr(route, "methods", None)}')
    print('==============================\n')
    yield
    logger.info('应用关闭中...')


def create_app() -> FastAPI:
    app = FastAPI(
        title='AIhub-Afdian',
        description='爱发电 Webhook 自动生成 New API 兑换码',
        version='1.0.0',
        lifespan=lifespan,
        redirect_slashes=False,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_methods=['GET', 'POST', 'OPTIONS'],
        allow_headers=['*'],
    )

    from app.api.v1.endpoints import afdian_webhook

    print('afdian_webhook.router.routes:', afdian_webhook.router.routes)
    app.include_router(afdian_webhook.router, prefix='/api/v1/afdian')
    print('注册完成。')

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f'全局异常: {exc}', exc_info=True)
        return JSONResponse(
            status_code=500,
            content={'code': 500, 'msg': f'服务器内部错误: {str(exc)}'},
        )

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

    @app.get('/test-ip')
    async def get_outbound_ip():
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get('https://api.ipify.org')
            return {'outbound_ip': resp.text}

    return app


app = create_app()

if __name__ == '__main__':
    from dotenv import load_dotenv

    load_dotenv()  # 仅在直接运行时加载 .env
    import uvicorn

    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)
