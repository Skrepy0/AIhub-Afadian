import os
from fastapi import Request, HTTPException


async def verify_afdian_webhook(request: Request):
    auth_header = request.headers.get('Authorization')
    print(f'🔍 Authorization header: {auth_header}')
    if not auth_header:
        raise HTTPException(
            status_code=401, detail='Missing Authorization header'
        )

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise HTTPException(
            status_code=401, detail='Invalid Authorization format'
        )

    token = parts[1]
    expected = os.getenv('AFDIAN_TOKEN')
    print(f'🔍 收到的 token: {token}')
    print(f'🔍 预期的 token: {expected}')
    if not expected:
        raise HTTPException(status_code=500, detail='AFDIAN_TOKEN not set')
    if token != expected:
        raise HTTPException(status_code=401, detail='Invalid token')
    return True
