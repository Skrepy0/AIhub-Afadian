import os
from fastapi import Request, HTTPException


async def verify_afdian_webhook(request: Request):
    """
    专门用于验证爱发电 Webhook 的依赖。
    检查 Authorization 头是否为 Bearer Token 格式。
    """
    if request.method == 'OPTIONS':
        return True

    auth_header = request.headers.get('Authorization')
    if not auth_header:
        raise HTTPException(
            status_code=401, detail='Missing Authorization header'
        )

    # 格式: "Bearer xxx"
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise HTTPException(
            status_code=401, detail='Invalid Authorization header format'
        )

    token = parts[1]
    expected_token = os.getenv('AFDIAN_TOKEN', '')
    if not expected_token:
        raise HTTPException(
            status_code=500, detail='AFDIAN_TOKEN not configured'
        )

    if token != expected_token:
        raise HTTPException(status_code=401, detail='Invalid token')

    return True
