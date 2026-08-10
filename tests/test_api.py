import pytest
from unittest.mock import AsyncMock, patch

from app.api.v1.endpoints.afdian_webhook import (
    _processed_orders,
    process_afdian_order,
    AfdianWebhookPayload,
)


@pytest.mark.asyncio
async def test_webhook_success(client, valid_payload):
    """测试正常 Webhook 请求"""
    # 打印路由（调试用）
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
    assert response.json() == {'code': 0, 'msg': 'received'}


@pytest.mark.asyncio
async def test_webhook_unauthorized(client, valid_payload):
    """测试未授权请求"""
    response = await client.post('/api/v1/afdian/webhook', json=valid_payload)
    assert response.status_code == 401

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
async def test_process_order_success(valid_payload):
    """测试后台任务正常流程"""
    with patch(
        'app.api.v1.endpoints.afdian_webhook.generate_redemption_code',
        new_callable=AsyncMock,
    ) as mock_generate:
        mock_generate.return_value = 'CODE_ABC123'

        with patch(
            'app.api.v1.endpoints.afdian_webhook.send_code_to_user',
            new_callable=AsyncMock,
        ) as mock_send:
            payload = AfdianWebhookPayload(**valid_payload)
            _processed_orders.clear()

            await process_afdian_order(payload)

            mock_generate.assert_awaited_once_with('ORDER_12345', 10.0)
            mock_send.assert_awaited_once_with(
                'CODE_ABC123', 'ORDER_12345', 'user@example.com', '感谢支持'
            )
            assert 'ORDER_12345' in _processed_orders


@pytest.mark.asyncio
async def test_process_order_not_paid(invalid_payload):
    """测试未支付订单被忽略"""
    with patch(
        'app.api.v1.endpoints.afdian_webhook.generate_redemption_code',
        new_callable=AsyncMock,
    ) as mock_generate:
        payload = AfdianWebhookPayload(**invalid_payload)
        await process_afdian_order(payload)
        mock_generate.assert_not_called()


@pytest.mark.asyncio
async def test_process_order_already_processed(valid_payload):
    """测试重复订单被跳过"""
    _processed_orders['ORDER_12345'] = 'done'

    with patch(
        'app.api.v1.endpoints.afdian_webhook.generate_redemption_code',
        new_callable=AsyncMock,
    ) as mock_generate:
        payload = AfdianWebhookPayload(**valid_payload)
        await process_afdian_order(payload)
        mock_generate.assert_not_called()

    _processed_orders.clear()


@pytest.mark.asyncio
async def test_process_order_generate_failed(valid_payload):
    """测试兑换码生成失败"""
    with patch(
        'app.api.v1.endpoints.afdian_webhook.generate_redemption_code',
        new_callable=AsyncMock,
    ) as mock_generate:
        mock_generate.return_value = None

        with patch(
            'app.api.v1.endpoints.afdian_webhook.send_code_to_user',
            new_callable=AsyncMock,
        ) as mock_send:
            payload = AfdianWebhookPayload(**valid_payload)
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
