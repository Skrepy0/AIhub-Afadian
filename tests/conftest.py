import os
import pytest
from httpx import AsyncClient, ASGITransport

# 设置测试环境变量
os.environ.setdefault('NEW_API_BASE_URL', 'https://test.example.com')
os.environ.setdefault('NEW_API_ADMIN_TOKEN', 'sk-test-token')
os.environ.setdefault('AFDIAN_TOKEN', 'test-token')
os.environ.setdefault('DEFAULT_QUOTA', '100')

from main import create_app


@pytest.fixture(scope='session')
def app():
    return create_app()


@pytest.fixture(scope='function')
def client(app):
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url='http://test',
    )


@pytest.fixture
def valid_payload():
    return {
        'data': {
            'out_trade_no': 'ORDER_12345',
            'total_amount': '10.00',
            'status': 2,
            'custom_order_id': 'user@example.com',
            'remark': '感谢支持',
        }
    }


@pytest.fixture
def invalid_payload():
    return {
        'data': {
            'out_trade_no': 'ORDER_67890',
            'total_amount': '5.00',
            'status': 1,
            'custom_order_id': None,
            'remark': None,
        }
    }
