#!/bin/bash
# ============================================
# AIhub-Afdian 后端服务管理脚本
# 用法：
#   ./start.sh              - 直接运行（开发模式）
#   ./start.sh {start|stop|restart|status|logs}  - systemd 服务管理
# ============================================

set -e

# 切换到脚本所在目录（项目根目录）
cd "$(dirname "$0")"

SERVICE_NAME="aihub-backend"
PROJECT_DIR="$(pwd)"

# ---------- 颜色输出 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}✅${NC} $1"; }
warn() { echo -e "${YELLOW}⚠️${NC} $1"; }
error() { echo -e "${RED}❌${NC} $1"; }
step() { echo -e "${BLUE}➜${NC} $1"; }

# ---------- 检查 systemd 服务是否存在 ----------
check_service() {
    if ! systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
        error "systemd 服务 ${SERVICE_NAME} 未安装"
        echo "请先创建服务文件: /etc/systemd/system/${SERVICE_NAME}.service"
        exit 1
    fi
}

# ---------- 直接运行（开发模式） ----------
run_direct() {
    # 检查虚拟环境
    if [ ! -d ".venv" ]; then
        error "未找到虚拟环境 .venv，请先创建"
        exit 1
    fi

    # 激活虚拟环境
    source .venv/bin/activate

    # 加载 .env
    if [ -f ".env" ]; then
        step "加载环境变量: .env"
        set -a
        source .env
        set +a
    else
        warn "未找到 .env 文件"
    fi

    # 默认参数
    HOST="${HOST:-127.0.0.1}"
    PORT="${PORT:-8000}"
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
                echo ""
                echo "服务管理命令:"
                echo "  ./start.sh start    - 启动 systemd 服务"
                echo "  ./start.sh stop     - 停止 systemd 服务"
                echo "  ./start.sh restart  - 重启 systemd 服务"
                echo "  ./start.sh status   - 查看服务状态"
                echo "  ./start.sh logs     - 查看服务日志"
                exit 0
                ;;
            *)
                error "未知参数: $1"
                echo "使用 --help 查看帮助"
                exit 1
                ;;
        esac
    done

    info "启动服务: http://$HOST:$PORT"
    info "Reload: ${RELOAD_FLAG:-关闭}"

    # 启动 uvicorn
    exec uvicorn main:app --host "$HOST" --port "$PORT" $RELOAD_FLAG
}

# ---------- systemd 服务管理 ----------
service_start() {
    check_service
    step "启动 ${SERVICE_NAME} 服务..."
    sudo systemctl start "$SERVICE_NAME"
    sudo systemctl status "$SERVICE_NAME" --no-pager
}

service_stop() {
    check_service
    step "停止 ${SERVICE_NAME} 服务..."
    sudo systemctl stop "$SERVICE_NAME"
    info "服务已停止"
}

service_restart() {
    check_service
    step "重启 ${SERVICE_NAME} 服务..."
    sudo systemctl restart "$SERVICE_NAME"
    sudo systemctl status "$SERVICE_NAME" --no-pager
}

service_status() {
    check_service
    sudo systemctl status "$SERVICE_NAME" --no-pager
}

service_logs() {
    check_service
    sudo journalctl -u "$SERVICE_NAME" -f
}

# ---------- 主入口 ----------
case "$1" in
    start)
        service_start
        ;;
    stop)
        service_stop
        ;;
    restart)
        service_restart
        ;;
    status)
        service_status
        ;;
    logs)
        service_logs
        ;;
    --help|-h)
        run_direct --help
        ;;
    *)
        run_direct "$@"
        ;;
esac