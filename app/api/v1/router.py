from fastapi import APIRouter

from app.api.v1.endpoints import afdian_webhook

router = APIRouter()

router.include_router(
    afdian_webhook.router,
    prefix='/afdian',
    tags=['afdian'],
)
