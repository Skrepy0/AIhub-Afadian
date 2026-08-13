import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os

# 强制设置测试环境变量（用直接赋值覆盖任何已有值）
os.environ['PYTEST_RUNNING'] = '1'
os.environ['NEW_API_BASE_URL'] = 'https://test.example.com'
os.environ['NEW_API_ADMIN_TOKEN'] = 'sk-test-token'
os.environ['AFDIAN_TOKEN'] = (
    'test-token'  # 注意这里是直接赋值，不是 setdefault
)
os.environ['DEFAULT_QUOTA'] = '100'

import pytest
from httpx import AsyncClient, ASGITransport

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
        'ec': 200,
        'em': 'ok',
        'data': {
            'type': 'order',
            'order': {
                'out_trade_no': '20210623213XXX83454010626',
                'user_id': 'adf397fe83748XXXcee52540025c377',
                'plan_id': 'a45353328af91XXX73052540025c377',
                'month': 1,
                'total_amount': '5.00',
                'show_amount': '5.00',
                'status': 2,
                'remark': '',
                'redeem_id': '',
                'product_type': 0,
                'discount': '0.00',
                'sku_detail': [],
                'address_person': '',
                'address_phone': '',
                'address_address': '',
            },
            'sign': 'xxxxxxxx',
        },
    }


@pytest.fixture
def invalid_payload():
    return {
        'ec': 200,
        'em': 'ok',
        'data': {
            'order': {
                'out_trade_no': 'ORDER_67890',
                'total_amount': '5.00',
                'status': 1,
                'remark': '',
            }
        },
    }
