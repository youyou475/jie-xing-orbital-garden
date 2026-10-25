#!/bin/bash
# 《借星》网页漫游一键启动
# 2026-10-23 更新：修复「双击后浏览器仍显示旧界面」问题
#   原因：浏览器缓存 + open 命令只激活已有标签页不刷新
#   对策：① 启动前清理占用 8802 端口的陈旧服务
#        ② 打开带时间戳的 URL，强制浏览器开新标签并重新加载全部资源
cd "$(dirname "$0")"
PORT=8802

echo "正在清理端口 $PORT 上的陈旧服务…"
lsof -ti tcp:$PORT 2>/dev/null | xargs kill -9 2>/dev/null
sleep 0.5

STAMP=$(date +%s)
echo "正在启动本地服务：http://localhost:$PORT"
echo "关闭此窗口即停止服务。"
echo ""
echo "如浏览器仍显示旧界面：按 Cmd+Shift+R 强刷，"
echo "或直接双击同目录下的 standalone.html（单文件版，零缓存风险）。"

( sleep 1.2 && open "http://localhost:$PORT/index.html?t=$STAMP" ) &
exec python3 -m http.server "$PORT"
