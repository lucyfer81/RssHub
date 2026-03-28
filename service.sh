#!/bin/bash
# RssHub 服务管理脚本

# 配置
PROJECT_DIR="/home/ubuntu/PyProjects/RssHub"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
PID_FILE="$PROJECT_DIR/.service.pid"
LOG_FILE="$PROJECT_DIR/logs/service.log"
HOST="0.0.0.0"
PORT=5005

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")"

# 获取 PID
get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    fi
}

# 检查服务是否运行
is_running() {
    local pid=$(get_pid)
    if [ -z "$pid" ]; then
        return 1
    fi
    ps -p "$pid" > /dev/null 2>&1
}

# 启动服务
start() {
    if is_running; then
        echo "服务已在运行中 (PID: $(get_pid))"
        return 1
    fi

    echo "启动 RssHub 服务..."
    cd "$PROJECT_DIR" || exit 1

    nohup "$VENV_PYTHON" -m uvicorn app.main:app \
        --host "$HOST" \
        --port "$PORT" \
        >> "$LOG_FILE" 2>&1 &

    echo $! > "$PID_FILE"
    sleep 2

    if is_running; then
        echo "✓ 服务启动成功 (PID: $(get_pid))"
        echo "  日志: $LOG_FILE"
        echo "  地址: http://$HOST:$PORT"
    else
        echo "✗ 服务启动失败，请查看日志: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

# 停止服务
stop() {
    if ! is_running; then
        echo "服务未运行"
        rm -f "$PID_FILE"
        return 0
    fi

    local pid=$(get_pid)
    echo "停止服务 (PID: $pid)..."
    kill "$pid"

    # 等待进程结束（最多 10 秒）
    for i in {1..10}; do
        if ! is_running; then
            rm -f "$PID_FILE"
            echo "✓ 服务已停止"
            return 0
        fi
        sleep 1
    done

    # 强制结束
    echo "强制停止服务..."
    kill -9 "$pid" 2>/dev/null
    rm -f "$PID_FILE"
    echo "✓ 服务已强制停止"
}

# 重启服务
restart() {
    stop
    sleep 1
    start
}

# 显示状态
status() {
    echo "=== RssHub 服务状态 ==="

    if is_running; then
        local pid=$(get_pid)
        echo "状态: 运行中"
        echo "PID: $pid"
        echo "端口: $PORT"
        echo "地址: http://$HOST:$PORT"

        # 显示进程信息
        echo ""
        echo "进程信息:"
        ps -p "$pid" -o pid,ppid,cmd,etime,pcpu,pmem 2>/dev/null || echo "  无法获取进程信息"

        # 检查端口监听
        if command -v netstat >/dev/null 2>&1; then
            echo ""
            echo "端口监听:"
            netstat -tlnp 2>/dev/null | grep ":$PORT " || echo "  端口 $PORT 未监听"
        elif command -v ss >/dev/null 2>&1; then
            echo ""
            echo "端口监听:"
            ss -tlnp 2>/dev/null | grep ":$PORT " || echo "  端口 $PORT 未监听"
        fi
    else
        echo "状态: 未运行"
        rm -f "$PID_FILE"
    fi
}

# 显示日志
logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "日志文件不存在: $LOG_FILE"
    fi
}

# 显示帮助
usage() {
    echo "用法: $0 {start|stop|restart|status|logs}"
    echo ""
    echo "命令:"
    echo "  start    - 启动服务"
    echo "  stop     - 停止服务"
    echo "  restart  - 重启服务"
    echo "  status   - 查看状态"
    echo "  logs     - 查看实时日志"
}

# 交互式菜单
interactive() {
    while true; do
        clear
        echo ""
        echo "════════════════════════════════════════"
        echo "        RssHub 服务管理"
        echo "════════════════════════════════════════"
        echo ""

        # 显示当前状态
        if is_running; then
            echo "当前状态: ● 运行中 (PID: $(get_pid))"
        else
            echo "当前状态: ○ 未运行"
        fi

        echo ""
        echo "  1) 启动服务"
        echo "  2) 停止服务"
        echo "  3) 重启服务"
        echo "  4) 查看状态"
        echo "  5) 查看日志"
        echo "  0) 退出"
        echo ""
        echo -n "请选择 [0-5]: "

        read -r choice

        case $choice in
            1)
                echo ""
                start
                echo ""
                echo "按回车继续..."
                read -r
                ;;
            2)
                echo ""
                stop
                echo ""
                echo "按回车继续..."
                read -r
                ;;
            3)
                echo ""
                restart
                echo ""
                echo "按回车继续..."
                read -r
                ;;
            4)
                echo ""
                status
                echo ""
                echo "按回车继续..."
                read -r
                ;;
            5)
                echo ""
                echo "查看日志 (按 Ctrl+C 退出日志查看)"
                sleep 1
                logs
                ;;
            0|q|Q)
                echo ""
                echo "再见!"
                exit 0
                ;;
            *)
                echo ""
                echo "无效选择，请重试..."
                sleep 1
                ;;
        esac
    done
}

# 主逻辑
case "${1:-}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    "")
        interactive
        ;;
    *)
        usage
        exit 1
        ;;
esac
