import asyncio
import json
import logging
import os
import re
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

DEFAULT_QUOTA = int(os.getenv('DEFAULT_QUOTA', '100'))

# ---------- 幂等存储（生产环境用 Redis） ----------
_processed_orders: Dict[str, str] = {}

# ---------- HTTP 客户端 ----------
_http_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=10),
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
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ['code', 'redemption_code', 'token']:
                if key in data and data[key]:
                    return data[key]
            codes = data.get('redemption_codes', [])
            if codes and isinstance(codes, list) and codes[0]:
                return codes[0]

    for key in ['code', 'redemption_code', 'token']:
        if key in response_data and response_data[key]:
            return response_data[key]

    return None


# ---------- 核心业务 ----------
async def generate_redemption_code(
    order_id: str, amount: float, retries: int = 3
) -> Optional[str]:
    """调用 New API 生成兑换码，带重试机制"""
    quota = int(parse_amount(str(amount)) * 10) or DEFAULT_QUOTA
    url = f'{NEW_API_BASE_URL.rstrip("/")}/api/redemption/'
    headers = {
        'Authorization': f'Bearer {NEW_API_ADMIN_TOKEN}',
        'Content-Type': 'application/json',
    }
    payload = {'name': f'afdian_{order_id}', 'quota': quota}

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


async def send_code_to_user(
    code: str, order_id: str, custom_id: Optional[str], remark: Optional[str]
):
    """
    将兑换码写入爱发电订单备注，用户可在订单详情中查看。
    """
    AFDIAN_API_BASE = 'https://afdian.net/api/open'
    url = f'{AFDIAN_API_BASE}/update-order-remark'
    headers = {
        'Content-Type': 'application/json',
        # 爱发电官方推荐使用 Bearer Token 鉴权
        'Authorization': f'Bearer {AFDIAN_TOKEN}',
    }
    payload = {
        'out_trade_no': order_id,
        'remark': f'🎉 您的兑换码: {code} (请妥善保管)',
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            if result.get('ec') == 200:
                logger.info(f'✅ 订单 {order_id} 备注更新成功，兑换码: {code}')
            else:
                logger.error(
                    f'❌ 备注更新失败: {result.get("em", "未知错误")}'
                )
                # 降级：如果备注失败，尝试发邮件（如果有邮箱）
    #             if custom_id and "@" in custom_id:
    #                 await send_code_by_email(code, custom_id, order_id)
    except Exception as e:
        logger.error(f'❌ 调用备注 API 失败: {e}')
        # 降级方案：通过邮件发送
        # if custom_id and "@" in custom_id:
        #     await send_code_by_email(code, custom_id, order_id)


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
    # custom_id 可忽略或用 remark

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

    code = await generate_redemption_code(order_id, amount)
    if not code:
        logger.error(f'订单 {order_id} 生成兑换码失败，需人工介入')
        return

    _processed_orders[order_id] = 'done'
    await send_code_to_user(code, order_id, None, remark)  # custom_id 无


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
