import base64
import json
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import Request, HTTPException


def get_afdian_public_key() -> str:
    """从环境变量或默认值获取公钥"""
    env_key = os.getenv('AFDIAN_PUBLIC_KEY')
    if env_key:
        return env_key.replace('\\n', '\n')
    '读取公钥失败'
    return ''


def verify_afdian_signature(order_data: dict, sign: str) -> bool:
    """验证爱发电 Webhook 签名"""
    sign_str = (
        order_data.get('out_trade_no', '')
        + order_data.get('user_id', '')
        + order_data.get('plan_id', '')
        + order_data.get('total_amount', '')
    )
    try:
        public_key_pem = get_afdian_public_key()
        if not public_key_pem:
            return False
        public_key = load_pem_public_key(
            public_key_pem.encode(), backend=default_backend()
        )
        public_key.verify(
            base64.b64decode(sign),
            sign_str.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


async def verify_afdian_webhook(request: Request) -> bool:
    """验证爱发电 Webhook 请求（安全修复版）"""
    # ---------- 1. Bearer Token 验证 ----------
    if os.getenv('ENABLE_BEARER_AUTH', 'false').lower() == 'true':
        auth_header = request.headers.get('Authorization')
        if auth_header:
            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != 'bearer':
                raise HTTPException(
                    status_code=401, detail='Invalid Authorization format'
                )
            token = parts[1]
            expected = os.getenv('AFDIAN_TOKEN')
            if not expected:
                raise HTTPException(
                    status_code=500, detail='AFDIAN_TOKEN not set'
                )
            if token != expected:
                raise HTTPException(status_code=401, detail='Invalid token')
            return True

    # ---------- 2. 签名验证 ----------
    try:
        body = await request.body()
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid JSON body')

    sign = data.get('sign')
    if not sign:
        raise HTTPException(status_code=403, detail='Missing signature')

    order_data = data.get('data', {}).get('order', {})
    if not order_data:
        raise HTTPException(status_code=400, detail='Missing order data')

    # 检查必要字段是否完整
    required_fields = ['out_trade_no', 'user_id', 'plan_id', 'total_amount']
    if not all(field in order_data for field in required_fields):
        raise HTTPException(status_code=400, detail='Incomplete order data')

    if verify_afdian_signature(order_data, sign):
        return True
    else:
        raise HTTPException(status_code=403, detail='Invalid signature')
