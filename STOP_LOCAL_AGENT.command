#!/bin/bash
# set -u disabled for macOS compatibility

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$ROOT/.local-agent-run"

say() { printf "[Local Agent] %s\n" "$1"; }

process_cwd() {
  lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

is_our_process() {
  local pid service cwd cmd
  pid="${1:-}"
  service="${2:-}"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  cwd="$(process_cwd "$pid")"
  cmd="$(ps -ww -p "$pid" -o command= 2>/dev/null || true)"

  case "$service" in
    backend)
      [[ "$cwd" == "$ROOT" && "$cmd" == *"uvicorn backend.main:app"* ]]
      ;;
    frontend)
      [[ "$cwd" == "$ROOT/frontend" ]] &&
        { [[ "$cmd" == *"npm run dev"* ]] || [[ "$cmd" == *"vite"* ]]; }
      ;;
    *) return 1 ;;
  esac
}

stop_pid() {
  local pid service i
  pid="${1:-}"
  service="${2:-}"

  if ! is_our_process "$pid" "$service"; then return 1; fi

  say "正在停止 ${3:-${2:-service}}（PID $pid）..."
  kill -TERM "$pid" 2>/dev/null || true

  for i in {1..8}; do
    if ! kill -0 "$pid" 2>/dev/null || ! is_our_process "$pid" "$service"; then
      say "${3:-${2:-service}} 已停止。"
      return 0
    fi
    sleep 1
  done

  if is_our_process "$pid" "$service"; then
    say "${3:-${2:-service}} 未能正常退出，正在强制结束..."
    kill -KILL "$pid" 2>/dev/null || true
    sleep 1
  fi
  ! is_our_process "$pid" "$service"
}

stop_service() {
  local service port pid_file pid pids found
  service="${1:-}"
  port="${2:-}"
  pid_file="$RUN_DIR/$service.pid"
  found=0

  # First try the PID recorded when the service was launched.
  if [ -f "$pid_file" ]; then
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
      if stop_pid "$pid" "$service" "$service"; then found=1; fi
    fi
    rm -f "$pid_file"
  fi

  # Then inspect the listener on the expected project port.
  pids="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      if is_our_process "$pid" "$service"; then
        if stop_pid "$pid" "$service" "$service listener"; then found=1; fi
      fi
    done <<< "$pids"
  fi

  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    say "警告：端口 $port 仍被占用，但进程未通过项目身份校验；为安全起见没有终止它。"
  elif [ "$found" -eq 0 ]; then
    say "$service 当前未运行。"
  fi
}

printf "\n[Local Agent] 正在自动关闭本项目服务...\n"
stop_service backend 8000
stop_service frontend 5173

rm -f "$RUN_DIR/backend.pid" "$RUN_DIR/frontend.pid"

if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  say "后端端口 8000 仍被占用，请检查上方警告。"
else
  say "Backend :8000 已关闭。"
fi
if lsof -nP -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
  say "前端端口 5173 仍被占用，请检查上方警告。"
else
  say "Frontend :5173 已关闭。"
fi
say "Ollama :11434 保持运行，不会被关闭。"
read -r -p "按回车关闭此窗口..." _
