#!/bin/bash
# ============================================
# AIhub-Afdian 后端服务启动脚本
# 用法：./start.sh [--reload] [--port 8000]
# ============================================

set -e  # 遇到错误立即退出

# 切换到脚本所在目录（项目根目录）
cd "$(dirname "$0")"

echo "📂 当前目录: $(pwd)"

# 检查虚拟环境是否存在
if [ ! -d ".venv" ]; then
    echo "❌ 错误：未找到虚拟环境 .venv，请先创建"
    exit 1
fi

# 激活虚拟环境
source .venv/bin/activate

# 加载 .env 环境变量（如果存在）
if [ -f ".env" ]; then
    echo "📄 加载环境变量: .env"
    set -a
    source .env
    set +a
else
    echo "⚠️ 警告：未找到 .env 文件，请确保所需环境变量已设置"
fi

# 默认参数
HOST="127.0.0.1"
PORT="8000"
RELOAD_FLAG=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --reload)
            RELOAD_FLAG="--reload"
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --help|-h)
            echo "用法: ./start.sh [选项]"
            echo "选项:"
            echo "  --reload        开启自动重载（开发模式）"
            echo "  --port PORT     指定端口 (默认: 8000)"
            echo "  --host HOST     指定主机 (默认: 127.0.0.1)"
            echo "  --help, -h      显示帮助信息"
            exit 0
            ;;
        *)
            echo "❌ 未知参数: $1"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
    esac
done

echo "🚀 启动服务: http://$HOST:$PORT"
echo "   Reload: ${RELOAD_FLAG:-关闭}"

# 启动 uvicorn
exec uvicorn main:app --host "$HOST" --port "$PORT" $RELOAD_FLAG