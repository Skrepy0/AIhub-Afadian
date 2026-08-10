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
            'order': {
                'out_trade_no': 'ORDER_12345',
                'total_amount': '10.00',
                'status': 2,
                'remark': '感谢支持',
            }
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
