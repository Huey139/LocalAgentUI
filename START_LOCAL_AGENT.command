#!/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$ROOT/.local-agent-run"
mkdir -p "$RUN_DIR"
BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"

say() { printf "\n[Local Agent] %s\n" "$1"; }
fail() { say "错误：$1"; read -r -p "按回车关闭窗口..." _; exit 1; }

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ -s "$NVM_DIR/nvm.sh" ]; then . "$NVM_DIR/nvm.sh"; fi

command -v python3 >/dev/null 2>&1 || fail "找不到 python3。"
command -v node >/dev/null 2>&1 || fail "找不到 Node.js。"
command -v npm >/dev/null 2>&1 || fail "找不到 npm。"

port_is_listening() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

process_cwd() {
  lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

is_our_listener() {
  local port="$1" expected_cwd="$2" expected_cmd="$3" pids pid cwd cmd
  pids="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  [ -n "$pids" ] || return 1
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    cwd="$(process_cwd "$pid")"
    cmd="$(ps -ww -p "$pid" -o command= 2>/dev/null || true)"
    if [ "$cwd" = "$expected_cwd" ] && [[ "$cmd" == *"$expected_cmd"* ]]; then
      return 0
    fi
  done <<< "$pids"
  return 1
}

say "项目目录：$ROOT"
say "检查并启动后端（端口 8000）..."
if port_is_listening 8000; then
  is_our_listener 8000 "$ROOT" "uvicorn backend.main:app" || fail "端口 8000 已被其他程序占用；为避免误操作，没有启动或关闭该进程。"
  say "检测到本项目后端已经运行，不重复启动。"
else
  if [ ! -d "$ROOT/.venv" ]; then
    say "首次运行：创建 Python 虚拟环境并安装后端依赖..."
    python3 -m venv "$ROOT/.venv" || fail "创建 Python 虚拟环境失败。"
    "$ROOT/.venv/bin/python" -m pip install --quiet -r "$ROOT/backend/requirements.txt" || fail "安装后端依赖失败。"
  elif ! "$ROOT/.venv/bin/python" -c "import uvicorn, fastapi" >/dev/null 2>&1; then
    say "检查到后端依赖不完整，正在安装..."
    "$ROOT/.venv/bin/python" -m pip install --quiet -r "$ROOT/backend/requirements.txt" || fail "安装后端依赖失败。"
  fi
  (
    cd "$ROOT"
    nohup "$ROOT/.venv/bin/python" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 >"$BACKEND_LOG" 2>&1 </dev/null &
    echo $! > "$RUN_DIR/backend.pid"
  )
fi

say "检查并启动前端（端口 5173）..."
if port_is_listening 5173; then
  is_our_listener 5173 "$ROOT/frontend" "vite" || fail "端口 5173 已被其他程序占用；为避免误操作，没有启动或关闭该进程。"
  say "检测到本项目前端已经运行，不重复启动。"
else
  if [ ! -d "$ROOT/frontend/node_modules" ]; then
    say "首次运行：安装前端依赖（可能需要几分钟）..."
    (cd "$ROOT/frontend" && npm install) || fail "前端依赖安装失败。"
  fi
  (
    cd "$ROOT/frontend"
    nohup npm run dev -- --host 127.0.0.1 >"$FRONTEND_LOG" 2>&1 </dev/null &
    echo $! > "$RUN_DIR/frontend.pid"
  )
fi

sleep 3
port_is_listening 8000 || { say "后端未能启动。最近日志："; tail -n 35 "$BACKEND_LOG" 2>/dev/null || true; fail "后端启动失败。"; }
port_is_listening 5173 || { say "前端未能启动。最近日志："; tail -n 35 "$FRONTEND_LOG" 2>/dev/null || true; fail "前端启动失败。"; }

say "Local Agent 已启动。"
say "前端：http://127.0.0.1:5173"
say "后端：http://127.0.0.1:8000"
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  say "提醒：暂未检测到 Ollama 服务。聊天模型可能无法响应，请先启动 Ollama。"
else
  say "Ollama 服务可访问。"
fi
open "http://127.0.0.1:5173" >/dev/null 2>&1 || true
say "关闭服务请双击同级目录中的 STOP_LOCAL_AGENT.command。"
read -r -p "启动完成。按回车关闭此窗口（服务会继续运行）..." _
