import asyncio
import hashlib
import json
import logging
import os
import re
import time
from typing import Optional, Dict, Any

import httpx
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from app.core.dependencies import verify_afdian_webhook

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------- 配置 ----------
AFDIAN_TOKEN = os.environ.get('AFDIAN_TOKEN')
if not AFDIAN_TOKEN:
    logger.error('AFDIAN_TOKEN 环境变量未设置')

NEW_API_BASE_URL = os.getenv('NEW_API_BASE_URL')
if not NEW_API_BASE_URL:
    raise ValueError('NEW_API_BASE_URL 环境变量未设置')

NEW_API_ADMIN_TOKEN = os.getenv('NEW_API_ADMIN_TOKEN')
if not NEW_API_ADMIN_TOKEN:
    raise ValueError('NEW_API_ADMIN_TOKEN 环境变量未设置')

AFDIAN_USER_ID = os.getenv('AFDIAN_USER_ID')
if not AFDIAN_USER_ID:
    logger.error('AFDIAN_USER_ID 环境变量未设置')

QUOTA_RATE = int(os.getenv('QUOTA_RATE'))
if not AFDIAN_USER_ID:
    logger.error('QUOTA_RATE 环境变量未设置')

DEFAULT_QUOTA = int(os.getenv('DEFAULT_QUOTA', '100'))

# ---------- 幂等存储（生产环境用 Redis） ----------
_processed_orders: Dict[str, str] = {}

# ---------- HTTP 客户端 ----------
_http_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        # 如果设置了 PYTEST_RUNNING=1，则禁用 SSL 验证
        verify = not (os.getenv('PYTEST_RUNNING') == '1')
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=10),
            verify=verify,
        )
    return _http_client


class AfdianOrder(BaseModel):
    out_trade_no: str
    total_amount: str
    status: int
    remark: Optional[str] = None


class AfdianWebhookPayload(BaseModel):
    ec: int
    em: str
    data: Dict[str, Any]


# ---------- 工具函数 ----------
def parse_amount(amount_str: str) -> float:
    """从可能包含货币符号的字符串中提取数字金额"""
    if not amount_str:
        return 0.0
    match = re.search(r'[\d.]+', amount_str.strip())
    return float(match.group()) if match else 0.0


def extract_code_from_response(response_data: Dict[str, Any]) -> Optional[str]:
    """从 New API 响应中提取兑换码，兼容多种格式"""
    if isinstance(response_data, str):
        return response_data

    data = response_data.get('data', {})
    if data:
        # 如果 data 是字符串
        if isinstance(data, str):
            return data
        # 如果 data 是字典
        if isinstance(data, dict):
            for key in ['code', 'redemption_code', 'token']:
                if key in data and data[key]:
                    return data[key]
            codes = data.get('redemption_codes', [])
            if codes and isinstance(codes, list) and codes[0]:
                return codes[0]
        # ✅ 新增：如果 data 是数组（兑换码列表）
        if isinstance(data, list) and data:
            return data[0]

    # 顶层直接包含 code
    for key in ['code', 'redemption_code', 'token']:
        if key in response_data and response_data[key]:
            return response_data[key]

    return None


# ---------- 核心业务 ----------
async def generate_redemption_code(
    order_id: str, amount: float, retries: int = 3
) -> Optional[str]:
    """调用 New API 生成兑换码，带重试机制"""
    quota = (
        int(parse_amount(str(amount)) * 500000 * QUOTA_RATE) or DEFAULT_QUOTA
    )
    url = f'{NEW_API_BASE_URL.rstrip("/")}/api/redemption/'
    headers = {
        'Authorization': f'Bearer {NEW_API_ADMIN_TOKEN}',
        'Content-Type': 'application/json',
    }
    payload = {'name': f'af_{order_id[:8]}', 'quota': quota, 'count': 1}

    client = await get_http_client()
    last_exception = None

    for attempt in range(1, retries + 1):
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            code = extract_code_from_response(result)
            if code:
                logger.info(f'兑换码生成成功，订单 {order_id}: {code}')
                return code
            logger.warning(f'第 {attempt} 次未提取到兑换码: {result}')
            if attempt < retries:
                await asyncio.sleep(1 * attempt)
        except Exception as e:
            logger.warning(f'第 {attempt}/{retries} 次请求失败: {e}')
            last_exception = e
            if attempt < retries:
                await asyncio.sleep(2 ** (attempt - 1))

    logger.error(
        f'兑换码生成最终失败，订单 {order_id}', exc_info=last_exception
    )
    return None


# ---------- 爱发电 API 签名函数 ----------
def generate_afdian_sign(
    user_id: str, params: dict, ts: int, token: str
) -> str:
    """
    生成爱发电 API 签名
    规则：md5(token + 按key排序拼接key和value)
    """
    params_str = json.dumps(params, separators=(',', ':'))
    sign_str = f'{token}params{params_str}ts{ts}user_id{user_id}'
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()


# ---------- 发送私信函数 ----------
async def send_code_to_user(
    code: str,
    order_id: str,
    recipient_user_id: str,  # 下单用户的 user_id
    custom_id: Optional[str] = None,
    remark: Optional[str] = None,
):
    """
    通过爱发电私信发送兑换码给用户。
    """
    if not AFDIAN_USER_ID or not AFDIAN_TOKEN:
        logger.error('❌ AFDIAN_USER_ID 或 AFDIAN_TOKEN 未配置，无法发送私信')
        return

    ts = int(time.time())
    params = {
        'recipient': recipient_user_id,
        'content': f'🎉 感谢您的赞助！\n您的兑换码为：{code}\n请妥善保管，兑换后失效。',
    }
    sign = generate_afdian_sign(AFDIAN_USER_ID, params, ts, AFDIAN_TOKEN)

    payload = {
        'user_id': AFDIAN_USER_ID,
        'params': json.dumps(params, separators=(',', ':')),
        'ts': ts,
        'sign': sign,
    }

    url = 'https://www.ifdian.net/api/open/send-msg'

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
            if result.get('ec') == 200:
                logger.info(
                    f'✅ 私信发送成功，订单 {order_id}，兑换码: {code}'
                )
            else:
                logger.error(
                    f'❌ 私信发送失败: {result.get("em", "未知错误")}'
                )
                # 可以在此添加降级方案（如邮件）
    except Exception as e:
        logger.error(f'❌ 调用私信 API 失败: {e}')


# ---------- 处理订单流程 ----------
async def process_afdian_order(payload: AfdianWebhookPayload):
    # 从 payload.data 中提取 order 对象
    order_data = payload.data.get('order')
    if not order_data:
        logger.error('无效的订单数据：缺少 order 字段')
        return

    order_id = order_data.get('out_trade_no')
    status = order_data.get('status')
    total_amount = order_data.get('total_amount', '0.00')
    remark = order_data.get('remark', '')
    recipient_user_id = order_data.get('user_id')  # 下单用户 ID
    custom_id = None  # 如果需要，可以从 order_data 中获取 custom_order_id

    if not recipient_user_id:
        logger.error(f'订单 {order_id} 缺少 user_id，无法发送私信')
        # 仍可继续生成兑换码，但发送会失败

    if status != 2:
        logger.info(f'订单 {order_id} 状态 {status}，忽略')
        return

    if order_id in _processed_orders:
        logger.info(f'订单 {order_id} 已处理，跳过')
        return

    amount = parse_amount(total_amount)
    if amount <= 0:
        logger.error(f'订单 {order_id} 金额无效: {total_amount}')
        return

    # 生成兑换码
    code = await generate_redemption_code(order_id, amount)
    if not code:
        logger.error(f'订单 {order_id} 生成兑换码失败，需人工介入')
        return

    # 标记已处理
    _processed_orders[order_id] = 'done'

    # 发送私信（如果 recipient_user_id 存在）
    if recipient_user_id:
        await send_code_to_user(
            code, order_id, recipient_user_id, custom_id, remark
        )
    else:
        logger.warning(
            f'订单 {order_id} 没有 user_id，无法发送私信，兑换码: {code}'
        )
        # 这里可以降级到邮件等


# ---------- Webhook 入口 ----------
@router.post('/webhook')
async def afdian_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    _verified=Depends(verify_afdian_webhook),
):
    try:
        raw_body = await request.body()
        payload_data = json.loads(raw_body)
        payload = AfdianWebhookPayload(**payload_data)
    except Exception as e:
        logger.error(f'解析 Webhook 失败: {e}')
        raise HTTPException(status_code=400, detail='Invalid request body')

    background_tasks.add_task(process_afdian_order, payload)

    return {'ec': 200, 'em': 'ok'}


# ---------- 清理资源 ----------
async def cleanup_http_client():
    global _http_client
    if _http_client:
        await _http_client.aclose()


router.add_event_handler('shutdown', cleanup_http_client)
