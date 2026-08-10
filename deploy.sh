#!/bin/bash
# ============================================
# AIhub-Afdian 项目部署脚本
# 用法：./deploy.sh
# 功能：强制同步远程代码、更新依赖、重启服务
# ============================================

set -e  # 遇到任何错误立即退出

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

# ---------- 获取脚本所在目录（项目根目录） ----------
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

info "项目目录: $PROJECT_DIR"

# ---------- 检查是否为 Git 仓库 ----------
if [ ! -d ".git" ]; then
    error "当前目录不是 Git 仓库，请确保项目通过 Git 管理。"
    exit 1
fi

# ---------- 备份 .env 文件（如果存在） ----------
if [ -f ".env" ]; then
    cp .env .env.backup
    info "已备份 .env 文件到 .env.backup"
fi

# ---------- 强制同步远程代码 ----------
step "强制同步远程代码（丢弃所有本地更改）..."
git fetch --all

# 保存当前分支名
CURRENT_BRANCH=$(git branch --show-current)

# 强制重置到远程分支（如果当前分支是 main 或 master）
if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
    git reset --hard "origin/$CURRENT_BRANCH"
else
    # 如果当前不在 main/master，切换到 main 并强制重置
    warn "当前不在 main/master 分支，切换到 main..."
    git checkout main || git checkout master
    git reset --hard "origin/$(git branch --show-current)"
fi

# 清理未跟踪的文件和目录（-fd 强制删除未跟踪的文件和目录）
step "清理未跟踪的文件..."
git clean -fd

info "代码已完全同步到远程最新版本"

# ---------- 检查并安装依赖 ----------
step "更新 Python 依赖..."
if command -v uv &> /dev/null; then
    info "使用 uv 同步依赖..."
    uv sync --no-dev
elif [ -f ".venv/bin/pip" ]; then
    info "使用 pip（虚拟环境）安装依赖..."
    .venv/bin/pip install -r requirements.txt
elif [ -f ".venv/bin/activate" ]; then
    info "激活虚拟环境并使用 pip..."
    source .venv/bin/activate
    if command -v pip &> /dev/null; then
        pip install -r requirements.txt
    else
        error "虚拟环境中未找到 pip，请检查虚拟环境是否完整。"
        exit 1
    fi
else
    warn "未检测到 uv 或虚拟环境，跳过依赖更新。"
fi

# ---------- 重启 systemd 服务 ----------
step "重启 systemd 服务..."
SERVICE_NAME="aihub-backend"

if systemctl is-active --quiet "$SERVICE_NAME"; then
    systemctl restart "$SERVICE_NAME"
    info "服务 $SERVICE_NAME 已重启"
else
    warn "服务 $SERVICE_NAME 未运行，尝试启动..."
    systemctl start "$SERVICE_NAME"
fi

# ---------- 等待服务启动 ----------
sleep 2

# ---------- 检查服务状态 ----------
step "检查服务状态..."
if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "✅ 服务 $SERVICE_NAME 运行正常"
else
    error "❌ 服务 $SERVICE_NAME 启动失败，请检查日志："
    systemctl status "$SERVICE_NAME" --no-pager
    exit 1
fi

# ---------- 显示最近的日志 ----------
step "最近日志（最后 10 行）："
journalctl -u "$SERVICE_NAME" -n 10 --no-pager

# ---------- 完成 ----------
info "🎉 部署完成！"