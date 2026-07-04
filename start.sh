#!/bin/bash
# 会理市AI数字人导游 - 一键启动脚本 (Linux/macOS)
# 日期：2026年4月20日

set -e  # 遇到错误时退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查命令是否存在
check_command() {
    if ! command -v $1 &> /dev/null; then
        log_error "$1 未安装，请先安装 $1"
        exit 1
    fi
}

# 显示横幅
show_banner() {
    echo -e "${BLUE}"
    echo "================================================"
    echo "  会理市AI数字人导游系统 - 一键启动脚本"
    echo "  版本: 1.0.0"
    echo "================================================"
    echo -e "${NC}"
}

# 检查环境
check_environment() {
    log_info "检查系统环境..."
    
    # 检查Python
    check_command python3
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    log_info "Python版本: $PYTHON_VERSION"
    
    # 检查pip
    check_command pip3
    PIP_VERSION=$(pip3 --version | awk '{print $2}')
    log_info "pip版本: $PIP_VERSION"
    
    # 检查虚拟环境
    if [ ! -d "venv" ]; then
        log_warning "虚拟环境不存在，将创建虚拟环境..."
    fi
    
    # 检查.env文件
    if [ ! -f ".env" ]; then
        log_warning ".env 文件不存在，将使用 .env.example 创建..."
        if [ -f ".env.example" ]; then
            cp .env.example .env
            log_info "已创建 .env 文件，请编辑该文件配置您的设置"
        else
            log_error ".env.example 文件不存在"
            exit 1
        fi
    fi
    
    log_success "环境检查完成"
}

# 创建虚拟环境
create_virtualenv() {
    log_info "创建Python虚拟环境..."
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        log_success "虚拟环境创建成功"
    else
        log_info "虚拟环境已存在"
    fi
    
    # 激活虚拟环境
    source venv/bin/activate
    log_info "虚拟环境已激活"
}

# 安装依赖
install_dependencies() {
    log_info "安装Python依赖..."
    
    # 升级pip
    pip install --upgrade pip
    
    # 安装依赖
    if [ -f "backend/requirements.txt" ]; then
        pip install -r backend/requirements.txt
        log_success "依赖安装完成"
    else
        log_error "requirements.txt 文件不存在"
        exit 1
    fi
}

# 构建知识库
build_knowledge_base() {
    log_info "构建知识库..."
    
    if [ -f "knowledge_base/build_kb.py" ]; then
        # 检查是否已经有知识库
        if [ -d "backend/chroma_db" ] && [ "$(ls -A backend/chroma_db 2>/dev/null)" ]; then
            log_info "知识库已存在，跳过构建"
            return
        fi
        
        # 运行构建脚本
        python knowledge_base/build_kb.py
        
        if [ $? -eq 0 ]; then
            log_success "知识库构建完成"
        else
            log_warning "知识库构建失败，使用示例数据"
            # 使用示例数据
            if [ -f "knowledge_base/build_kb_simple.py" ]; then
                python knowledge_base/build_kb_simple.py
            fi
        fi
    else
        log_warning "知识库构建脚本不存在，使用示例数据"
        if [ -f "knowledge_base/build_kb_simple.py" ]; then
            python knowledge_base/build_kb_simple.py
        fi
    fi
}

# 检查端口占用
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_warning "端口 $port 已被占用"
        return 1
    fi
    return 0
}

# 启动后端服务
start_backend() {
    log_info "启动后端服务..."
    
    # 检查端口
    PORT=$(grep -E "^PORT=" .env 2>/dev/null | cut -d'=' -f2 || echo "5000")
    if ! check_port $PORT; then
        log_error "端口 $PORT 已被占用，请修改 .env 文件中的 PORT 配置"
        exit 1
    fi
    
    # 检查Gunicorn
    if command -v gunicorn &> /dev/null; then
        # 使用Gunicorn启动（生产环境）
        log_info "使用Gunicorn启动服务 (生产模式)"
        
        # 获取配置
        WORKERS=$(grep -E "^GUNICORN_WORKERS=" .env 2>/dev/null | cut -d'=' -f2 || echo "4")
        WORKER_CLASS=$(grep -E "^GUNICORN_WORKER_CLASS=" .env 2>/dev/null | cut -d'=' -f2 || echo "sync")
        BIND=$(grep -E "^GUNICORN_BIND=" .env 2>/dev/null | cut -d'=' -f2 || echo "0.0.0.0:$PORT")
        
        # 启动命令
        gunicorn "backend.app:app" \
            --workers=$WORKERS \
            --worker-class=$WORKER_CLASS \
            --bind=$BIND \
            --access-logfile - \
            --error-logfile - \
            --timeout 120 \
            --reload &
        
        BACKEND_PID=$!
        log_info "后端服务PID: $BACKEND_PID"
        
    else
        # 使用Flask开发服务器启动（开发环境）
        log_info "使用Flask开发服务器启动 (开发模式)"
        
        # 设置环境变量
        export FLASK_APP=backend/app.py
        export FLASK_ENV=development
        
        # 启动Flask
        python -m flask run --host=0.0.0.0 --port=$PORT &
        
        BACKEND_PID=$!
        log_info "后端服务PID: $BACKEND_PID"
    fi
    
    # 等待服务启动
    sleep 3
    
    # 检查服务是否启动成功
    if curl -s http://localhost:$PORT > /dev/null; then
        log_success "后端服务启动成功"
        log_info "服务地址: http://localhost:$PORT"
    else
        log_error "后端服务启动失败"
        exit 1
    fi
}

# 启动前端服务（可选）
start_frontend() {
    log_info "启动前端服务..."
    
    # 检查是否安装了http-server
    if command -v http-server &> /dev/null; then
        # 使用http-server启动前端
        log_info "使用http-server启动前端"
        
        # 在后台启动http-server
        http-server frontend -p 3000 -c-1 --silent &
        FRONTEND_PID=$!
        log_info "前端服务PID: $FRONTEND_PID"
        log_info "前端地址: http://localhost:3000"
        
    elif command -v python3 &> /dev/null; then
        # 使用Python的http.server
        log_info "使用Python http.server启动前端"
        
        cd frontend
        python3 -m http.server 3000 &
        FRONTEND_PID=$!
        cd ..
        
        log_info "前端服务PID: $FRONTEND_PID"
        log_info "前端地址: http://localhost:3000"
        
    else
        log_warning "未找到合适的HTTP服务器，前端将以静态文件方式提供"
        log_info "您可以直接在浏览器中打开 frontend/index.html 文件"
    fi
}

# 显示系统信息
show_system_info() {
    log_info "系统信息:"
    echo "----------------------------------------"
    echo "后端API: http://localhost:$PORT"
    echo "前端页面: http://localhost:3000 (如果已启动)"
    echo "管理后台: http://localhost:3000/admin.html"
    echo "API文档: http://localhost:$PORT/"
    echo "健康检查: http://localhost:$PORT/api/health"
    echo "----------------------------------------"
    echo -e "${YELLOW}按 Ctrl+C 停止所有服务${NC}"
    echo "----------------------------------------"
}

# 清理函数
cleanup() {
    log_info "正在停止服务..."
    
    # 停止后端服务
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
        log_info "后端服务已停止"
    fi
    
    # 停止前端服务
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
        log_info "前端服务已停止"
    fi
    
    # 停用虚拟环境
    deactivate 2>/dev/null || true
    
    log_success "服务已完全停止"
    exit 0
}

# 主函数
main() {
    # 设置信号处理
    trap cleanup INT TERM
    
    # 显示横幅
    show_banner
    
    # 检查环境
    check_environment
    
    # 创建虚拟环境
    create_virtualenv
    
    # 安装依赖
    install_dependencies
    
    # 构建知识库
    build_knowledge_base
    
    # 启动后端服务
    start_backend
    
    # 启动前端服务（可选）
    read -p "是否启动前端服务？(y/n, 默认: y): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        log_info "跳过前端服务启动"
    else
        start_frontend
    fi
    
    # 显示系统信息
    show_system_info
    
    # 等待用户中断
    wait
}

# 运行主函数
main "$@"