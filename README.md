# AIhub-Afdian

一个基于 FastAPI 的爱发电 Webhook 服务。项目用于在用户赞助成功后，接收爱发电回调、调用 New API 自动生成兑换码，并通过爱发电私信与邮箱把兑换码发送给赞助用户。

## 主要功能

- 接收爱发电 Webhook 回调：提供 `/api/v1/afdian/webhook` 接口处理订单通知。
- 校验请求来源：支持 Bearer Token 校验，也支持基于 `sign` 的爱发电签名校验。
- 自动生成兑换码：根据订单金额调用 New API 生成对应额度的兑换码。
- 自动私信发码：在生成兑换码后，通过爱发电开放接口向下单用户发送私信。
- 幂等处理：对已处理订单进行去重，避免重复发码。
- 健康检查：提供 `/health` 接口，便于部署后检查服务状态。

## 处理流程

1. 爱发电向服务发送订单 Webhook。
2. 服务校验 Token 或签名。
3. 解析订单信息，检查订单支付状态。
4. 根据订单金额调用 New API 生成兑换码。
5. 通过爱发电私信接口把兑换码发送给赞助用户。

## 技术栈

- Python 3.12+
- FastAPI
- Uvicorn
- HTTPX
- Pydantic
- python-dotenv

## 项目结构

```text
.
├── app/
│   ├── api/v1/endpoints/afdian_webhook.py   # Webhook 核心逻辑
│   └── core/dependencies.py                 # 鉴权与签名校验
├── main.py                                  # 应用入口
├── start.sh                                 # 启动与服务管理脚本
├── deploy.sh                                # 部署脚本
├── tests/                                   # 接口与流程测试
├── pyproject.toml                           # 项目配置
└── requirements.txt                         # 依赖列表
```

## 环境变量

启动前请先配置 `.env`：

```env
AFDIAN_TOKEN=your_afdian_token
AFDIAN_USER_ID=your_afdian_user_id
AFDIAN_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
NEW_API_BASE_URL=https://your-new-api-domain
NEW_API_ADMIN_TOKEN=your_new_api_admin_token
QUOTA_RATE=1
DEFAULT_QUOTA=100
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
```

### 变量说明

- `AFDIAN_TOKEN`：爱发电 Token，同时用于 Bearer Token 校验和爱发电接口签名。
- `AFDIAN_USER_ID`：爱发电开放平台的用户 ID，用于发送私信。
- `AFDIAN_PUBLIC_KEY`：爱发电 Webhook 验签公钥。
- `NEW_API_BASE_URL`：New API 服务地址。
- `NEW_API_ADMIN_TOKEN`：New API 管理员令牌，用于创建兑换码。
- `QUOTA_RATE`：兑换额度倍率，实际额度按订单金额换算。
- `DEFAULT_QUOTA`：当换算结果无效时使用的默认额度。
- `SMTP_HOST`：SMTP主机
- `SMTP_PORT`：端口号
- `SMTP_USER`：地址
- `SMTP_PASSWORD`：访问密钥
- `SMTP_FROM`：地址

## 本地开发

### 1. 创建虚拟环境

推荐使用 `uv`：

```bash
uv venv
uv sync
```

如果不用 `uv`，也可以使用 `venv` + `pip`：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件，并填入上面的配置项。

### 3. 启动服务

使用脚本启动：

```bash
./start.sh --reload
```

或直接运行：

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 4. 访问接口

- 首页：`/`
- 健康检查：`/health`
- Swagger 文档：`/docs`
- Webhook 地址：`/api/v1/afdian/webhook`

## Webhook 调用方式

### Bearer Token 模式

适合测试或内部调用：

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/afdian/webhook" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_afdian_token" \
  -d '{
    "ec": 200,
    "em": "ok",
    "data": {
      "order": {
        "out_trade_no": "ORDER_12345",
        "total_amount": "10.00",
        "status": 2,
        "remark": "感谢支持",
        "user_id": "afdian_user_xxx"
      }
    }
  }'
```

### 返回示例

```json
{
  "ec": 200,
  "em": "ok"
}
```

## 测试

运行全部测试：

```bash
pytest tests/
```

或仅运行 API 测试：

```bash
pytest tests/test_api.py
```

## 部署

项目自带 `deploy.sh` 与 `start.sh`，适合部署到 Linux 服务器并通过 systemd 管理。

### 方式一：直接启动

```bash
./start.sh --host 0.0.0.0 --port 8000
```

开发环境可加 `--reload`。

### 方式二：systemd 管理

`start.sh` 支持以下命令：

```bash
./start.sh start
./start.sh stop
./start.sh restart
./start.sh status
./start.sh logs
```

其中默认服务名为：`aihub-backend`

### 方式三：使用部署脚本

```bash
./deploy.sh
```

部署脚本会执行以下操作：

1. 备份 `.env` 为 `.env.backup`
2. 从远程仓库同步最新代码
3. 更新依赖
4. 重启 `aihub-backend` systemd 服务
5. 输出最近日志

## 生产环境建议

- 为 `.env` 中的敏感变量做好权限控制。
- 使用 systemd、Nginx 或其他反向代理托管服务。
- 开启 HTTPS，确保 Webhook 与管理接口链路安全。
- 如果订单量较大，建议把当前内存中的幂等记录迁移到 Redis。
- 部署后优先检查 `/health` 和 `journalctl -u aihub-backend` 日志。

## 注意事项

- 当前幂等状态保存在进程内存中，服务重启后不会保留。
- `deploy.sh` 会执行强制同步并清理未跟踪文件，使用前请确认服务器本地没有需要保留的未提交改动。
- 生产环境应优先使用爱发电官方签名校验，不建议长期依赖测试用 Bearer Token 模式。
