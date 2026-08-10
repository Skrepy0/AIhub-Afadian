import asyncio
import os
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from app.api.v1.endpoints.afdian_webhook import (
    _processed_orders,
    process_afdian_order,
    AfdianWebhookPayload,
    generate_redemption_code,
)
from main import create_app


@pytest.mark.asyncio
async def test_webhook_success(client, valid_payload):
    """测试正常 Webhook 请求"""
    print('\n=== 已注册路由 ===')
    for route in client._transport.app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f'  {route.path} -> {route.methods}')
    print('==================\n')

    response = await client.post(
        '/api/v1/afdian/webhook',
        json=valid_payload,
        headers={'Authorization': 'Bearer test-token'},
    )

    assert response.status_code == 200
    # 修改断言：检查 ec 和 em 字段
    assert response.json() == {'ec': 200, 'em': 'ok'}


@pytest.mark.asyncio
async def test_webhook_unauthorized(client, valid_payload):
    """测试无效 token 应返回 401"""
    response = await client.post(
        '/api/v1/afdian/webhook',
        json=valid_payload,
        headers={'Authorization': 'Bearer wrong-token'},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_invalid_json(client):
    """测试无效 JSON"""
    response = await client.post(
        '/api/v1/afdian/webhook',
        content='not a json',
        headers={'Authorization': 'Bearer test-token'},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_process_order_success():
    """测试后台任务正常流程（使用新的数据结构）"""
    # 构造符合爱发电真实格式的 payload，包含 user_id
    payload_data = {
        'ec': 200,
        'em': 'ok',
        'data': {
            'order': {
                'out_trade_no': 'ORDER_12345',
                'total_amount': '10.00',
                'status': 2,
                'remark': '感谢支持',
                'user_id': 'user_123',  # ✅ 新增：用于接收私信
                # 其他字段省略
            }
        },
    }
    payload = AfdianWebhookPayload(**payload_data)

    with patch(
        'app.api.v1.endpoints.afdian_webhook.generate_redemption_code',
        new_callable=AsyncMock,
    ) as mock_generate:
        mock_generate.return_value = 'CODE_ABC123'

        with patch(
            'app.api.v1.endpoints.afdian_webhook.send_code_to_user',
            new_callable=AsyncMock,
        ) as mock_send:
            _processed_orders.clear()
            await process_afdian_order(payload)

            mock_generate.assert_awaited_once_with('ORDER_12345', 10.0)
            # ✅ 更新断言：新签名是 (code, order_id, recipient_user_id, custom_id, remark)
            mock_send.assert_awaited_once_with(
                'CODE_ABC123',
                'ORDER_12345',
                'user_123',  # recipient_user_id
                None,  # custom_id
                '感谢支持',  # remark
            )
            assert 'ORDER_12345' in _processed_orders


@pytest.mark.asyncio
async def test_process_order_not_paid():
    """测试未支付订单被忽略"""
    payload_data = {
        'ec': 200,
        'em': 'ok',
        'data': {
            'order': {
                'out_trade_no': 'ORDER_67890',
                'total_amount': '5.00',
                'status': 1,  # 未支付
                'remark': '',
            }
        },
    }
    payload = AfdianWebhookPayload(**payload_data)

    with patch(
        'app.api.v1.endpoints.afdian_webhook.generate_redemption_code',
        new_callable=AsyncMock,
    ) as mock_generate:
        await process_afdian_order(payload)
        mock_generate.assert_not_called()


@pytest.mark.asyncio
async def test_process_order_already_processed():
    """测试重复订单被跳过"""
    payload_data = {
        'ec': 200,
        'em': 'ok',
        'data': {
            'order': {
                'out_trade_no': 'ORDER_12345',
                'total_amount': '10.00',
                'status': 2,
                'remark': '',
            }
        },
    }
    payload = AfdianWebhookPayload(**payload_data)
    _processed_orders['ORDER_12345'] = 'done'

    with patch(
        'app.api.v1.endpoints.afdian_webhook.generate_redemption_code',
        new_callable=AsyncMock,
    ) as mock_generate:
        await process_afdian_order(payload)
        mock_generate.assert_not_called()

    _processed_orders.clear()


@pytest.mark.asyncio
async def test_process_order_generate_failed():
    """测试兑换码生成失败"""
    payload_data = {
        'ec': 200,
        'em': 'ok',
        'data': {
            'order': {
                'out_trade_no': 'ORDER_12345',
                'total_amount': '10.00',
                'status': 2,
                'remark': '',
            }
        },
    }
    payload = AfdianWebhookPayload(**payload_data)

    with patch(
        'app.api.v1.endpoints.afdian_webhook.generate_redemption_code',
        new_callable=AsyncMock,
    ) as mock_generate:
        mock_generate.return_value = None

        with patch(
            'app.api.v1.endpoints.afdian_webhook.send_code_to_user',
            new_callable=AsyncMock,
        ) as mock_send:
            _processed_orders.clear()
            await process_afdian_order(payload)

            mock_send.assert_not_called()
            assert 'ORDER_12345' not in _processed_orders


@pytest.mark.asyncio
async def test_parse_amount():
    """测试金额解析"""
    from app.api.v1.endpoints.afdian_webhook import parse_amount

    assert parse_amount('10.00') == 10.0
    assert parse_amount('¥20.50') == 20.5
    assert parse_amount('$100.00') == 100.0
    assert parse_amount('12.34元') == 12.34
    assert parse_amount('') == 0.0
    assert parse_amount('invalid') == 0.0


@pytest.mark.asyncio
async def test_extract_code_from_response():
    """测试兑换码提取"""
    from app.api.v1.endpoints.afdian_webhook import extract_code_from_response

    assert extract_code_from_response('CODE_DIRECT') == 'CODE_DIRECT'
    assert (
        extract_code_from_response({'data': {'code': 'DATA_CODE'}})
        == 'DATA_CODE'
    )
    assert (
        extract_code_from_response(
            {'data': {'redemption_codes': ['CODE_ARRAY']}}
        )
        == 'CODE_ARRAY'
    )
    assert extract_code_from_response({'code': 'TOP_CODE'}) == 'TOP_CODE'
    assert extract_code_from_response({}) is None


@pytest.mark.asyncio
async def test_generate_redemption_code_success():
    """测试 generate_redemption_code 在 API 返回成功时正确提取兑换码"""
    # 创建模拟响应对象（同步方法）
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={'data': {'redemption_codes': ['CODE_SUCCESS']}}
    )
    mock_response.raise_for_status = MagicMock()  # 不抛出异常

    with patch(
        'httpx.AsyncClient.post', return_value=mock_response
    ) as mock_post:
        code = await generate_redemption_code('ORDER_TEST', 10.0)
        assert code == 'CODE_SUCCESS'
        mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_redemption_code_retry_then_success():
    """测试重试机制：前两次失败，第三次成功"""
    # 模拟失败响应（异常）
    # 模拟成功响应
    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.json = MagicMock(
        return_value={'data': {'code': 'CODE_RETRY'}}
    )
    mock_success.raise_for_status = MagicMock()

    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.side_effect = [
            Exception('Connection error'),  # 第一次失败
            Exception('HTTP 500'),  # 第二次失败
            mock_success,  # 第三次成功
        ]
        code = await generate_redemption_code('ORDER_RETRY', 10.0)
        assert code == 'CODE_RETRY'
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_generate_redemption_code_all_retries_fail():
    """测试所有重试都失败时返回 None"""
    with patch(
        'httpx.AsyncClient.post', side_effect=Exception('Network error')
    ) as mock_post:
        code = await generate_redemption_code('ORDER_FAIL', 10.0)
        assert code is None
        assert mock_post.call_count == 3  # 默认重试 3 次


@pytest.mark.asyncio
async def test_generate_redemption_code_parses_different_formats():
    """测试 extract_code_from_response 处理多种响应格式"""
    # 测试 data.redemption_codes 数组
    mock_response1 = MagicMock()
    mock_response1.status_code = 200
    mock_response1.json = MagicMock(
        return_value={'data': {'redemption_codes': ['CODE_ARRAY']}}
    )
    mock_response1.raise_for_status = MagicMock()

    with patch('httpx.AsyncClient.post', return_value=mock_response1):
        code = await generate_redemption_code('ORDER1', 10.0)
        assert code == 'CODE_ARRAY'

    # 测试 data.code
    mock_response2 = MagicMock()
    mock_response2.status_code = 200
    mock_response2.json = MagicMock(
        return_value={'data': {'code': 'CODE_OBJECT'}}
    )
    mock_response2.raise_for_status = MagicMock()

    with patch('httpx.AsyncClient.post', return_value=mock_response2):
        code = await generate_redemption_code('ORDER2', 10.0)
        assert code == 'CODE_OBJECT'

    # 测试顶层 code
    mock_response3 = MagicMock()
    mock_response3.status_code = 200
    mock_response3.json = MagicMock(return_value={'code': 'TOP_CODE'})
    mock_response3.raise_for_status = MagicMock()

    with patch('httpx.AsyncClient.post', return_value=mock_response3):
        code = await generate_redemption_code('ORDER3', 10.0)
        assert code == 'TOP_CODE'


@pytest.mark.asyncio
async def test_full_webhook_flow(client):
    """
    端到端测试：
    1. 模拟爱发电发送完整的 Webhook 数据
    2. 调用 /api/v1/afdian/webhook
    3. 验证 generate_redemption_code 和 send_code_to_user 被正确调用
    4. 验证幂等记录生效
    """
    payload = {
        'ec': 200,
        'em': 'ok',
        'data': {
            'order': {
                'out_trade_no': 'ORDER_E2E_001',
                'total_amount': '15.00',
                'status': 2,
                'remark': '用户备注',
                'user_id': 'fake_user',  # ✅ 用于接收私信
                'plan_id': 'fake_plan',
            }
        },
    }

    # 模拟 generate_redemption_code 返回兑换码
    with patch(
        'app.api.v1.endpoints.afdian_webhook.generate_redemption_code',
        return_value='E2E_CODE_123',
    ) as mock_generate:
        # 模拟 send_code_to_user 正常执行
        with patch(
            'app.api.v1.endpoints.afdian_webhook.send_code_to_user',
            new_callable=AsyncMock,
        ) as mock_send:
            _processed_orders.clear()  # 清空幂等记录

            # 发起请求（不携带认证头，模拟爱发电真实行为）
            response = await client.post(
                '/api/v1/afdian/webhook', json=payload
            )

    # 验证 Webhook 端点立即返回成功
    assert response.status_code == 200
    assert response.json() == {'ec': 200, 'em': 'ok'}

    # 等待后台任务完成（极短延迟确保异步任务执行）
    await asyncio.sleep(0.1)

    # 验证业务函数被调用
    mock_generate.assert_awaited_once_with('ORDER_E2E_001', 15.0)
    # ✅ 修改：增加 recipient_user_id 参数
    mock_send.assert_awaited_once_with(
        'E2E_CODE_123',
        'ORDER_E2E_001',
        'fake_user',  # recipient_user_id
        None,  # custom_id
        '用户备注',  # remark
    )

    # 验证幂等记录已写入
    assert 'ORDER_E2E_001' in _processed_orders


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_webhook_flow_real_new_api():
    # 检查环境变量
    if not os.getenv('NEW_API_BASE_URL') or not os.getenv(
        'NEW_API_ADMIN_TOKEN'
    ):
        pytest.skip('环境变量未设置')

    # 快速健康检查（使用 verify=False）
    try:
        async with httpx.AsyncClient(timeout=3.0, verify=False) as hc:
            await hc.get(f'{os.getenv("NEW_API_BASE_URL")}/health')
    except Exception as e:
        print(f'健康检查失败: {e}')
        pytest.skip('New API 服务不可达，跳过真实集成测试')

    app = create_app()
    client = AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test'
    )

    payload = {
        'ec': 200,
        'em': 'ok',
        'data': {
            'order': {
                'out_trade_no': 'ORDER_INTEGRATION_003',
                'total_amount': '1.00',
                'status': 2,
                'remark': '集成测试',
            }
        },
    }

    _processed_orders.clear()
    response = await client.post('/api/v1/afdian/webhook', json=payload)
    assert response.status_code == 200
    assert response.json() == {'ec': 200, 'em': 'ok'}

    await asyncio.sleep(1)

    # 如果成功，_processed_orders 应包含该订单
    assert 'ORDER_INTEGRATION_003' in _processed_orders
