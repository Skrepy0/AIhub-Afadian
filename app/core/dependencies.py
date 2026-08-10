import os

from fastapi import Request, HTTPException


async def verify_afdian_webhook(request: Request):
    auth_header = request.headers.get('Authorization')

    # 如果没有 Authorization 头，直接放行（爱发电原生请求）
    if not auth_header:
        return True

    # 如果有，则验证 Bearer Token
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise HTTPException(
            status_code=401, detail='Invalid Authorization format'
        )

    token = parts[1]
    expected = os.getenv('AFDIAN_TOKEN')
    if not expected:
        raise HTTPException(status_code=500, detail='AFDIAN_TOKEN not set')
    if token != expected:
        raise HTTPException(status_code=401, detail='Invalid token')

    return True
