#!/bin/sh
# ============================================================================
# 报表管理平台 —— 容器启动脚本
#   1) 准备"结果目录"（/flag 放诱饵文件，/root/root_flag.txt 放高权限验证值）
#   2) 首次启动时初始化数据库
#   3) 启动 Web 应用
# 说明：容器内以 root 运行（模拟"部署时未做降权"的常见情况），
#       因此拿到表达式求值能力后可读取位于高权限目录的验证值。
# ============================================================================
set -e

mkdir -p /app/data /flag

# ---- 高权限验证值（仅 root 可读）----
if [ ! -f /root/root_flag.txt ]; then
    if [ -n "$ROOT_FLAG" ]; then
        printf '%s\n' "$ROOT_FLAG" > /root/root_flag.txt
    else
        printf 'FLAG{root_level_%s}\n' "$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')" \
            > /root/root_flag.txt
    fi
    chmod 600 /root/root_flag.txt
fi

# ---- 诱饵文件（增加排查干扰）----
if [ ! -f /flag/note.txt ]; then
    cat > /flag/note.txt <<'EOF'
本目录为系统保留目录，用于存放平台运行期间产生的核对文件。
请勿在此目录中寻找与业务无关的内容。
EOF
fi

if [ ! -f /flag/temp_check.txt ]; then
    printf 'FLAG{this_is_a_decoy_not_the_real_one}\n' > /flag/temp_check.txt
fi

# ---- 初始化数据库（幂等）----
python /app/init_db.py

# ---- 启动应用 ----
exec python /app/app.py
