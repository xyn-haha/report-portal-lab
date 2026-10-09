# -*- coding: utf-8 -*-
"""
报表管理平台 —— 数据库初始化脚本

首次启动时自动执行，负责：
  1. 创建数据目录与 SQLite 数据库文件；
  2. 建表并插入初始业务数据（报表定义、系统配置）；
  3. 生成内部签名密钥与用户层 flag；
  4. 写入少量诱饵数据，增加排查难度。

重复执行时默认跳过（数据库已存在即不覆盖），可用 --force 强制重建。
"""

import argparse
import os
import secrets
import sqlite3
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "report.db")


def random_flag(prefix):
    return "FLAG{%s_%s}" % (prefix, secrets.token_hex(8))


SCHEMA = """
DROP TABLE IF EXISTS report_def;
DROP TABLE IF EXISTS sys_config;
DROP TABLE IF EXISTS sys_user;
DROP TABLE IF EXISTS sys_log;

-- 报表定义表：preview_expr 是高权限用户可维护的"预览表达式"字段，
-- 后端在执行报表时会读取它。
CREATE TABLE report_def (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    owner        TEXT NOT NULL,
    preview_expr TEXT NOT NULL,
    updated_at   TEXT
);

-- 系统配置表：内部约定、内部签名密钥等
CREATE TABLE sys_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    note  TEXT
);

-- 用户表：初始化后不写入任何可用账号
CREATE TABLE sys_user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL,
    enabled       INTEGER NOT NULL DEFAULT 1
);

-- 系统日志表（仅作展示，含诱饵内容）
CREATE TABLE sys_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT,
    level   TEXT,
    message TEXT
);
"""


def build_database(force=False):
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(DB_PATH) and not force:
        print("[init] 数据文件已存在，跳过初始化: %s" % DB_PATH)
        return

    sign_key = os.environ.get("INTERNAL_SIGN_KEY") or secrets.token_hex(16)
    user_flag = os.environ.get("USER_FLAG") or random_flag("user_level_report_access")
    decoy_flag = "FLAG{this_is_a_decoy_not_the_real_one}"

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript(SCHEMA)

    # ---- 报表定义（预览表达式均为正常业务表达式）----
    reports = [
        ("sales_summary", "销售汇总月报", "bi_team", 'report_total("sales_summary")'),
        ("inventory_snapshot", "库存快照日报", "scm_team", 'report_total("inventory_snapshot")'),
        ("finance_monthly", "财务月结报表", "fin_team", 'report_total("finance_monthly")'),
        ("ops_health", "运维健康巡检", "ops_team", 'report_total("ops_health")'),
    ]
    for name, title, owner, expr in reports:
        cur.execute(
            "INSERT INTO report_def (name, title, owner, preview_expr, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (name, title, owner, expr),
        )

    # ---- 系统配置 ----
    configs = [
        ("app_name", "report-portal", "应用名"),
        ("app_version", "1.4.2", "版本号"),
        ("internal_sign_key", sign_key, "内部接口签名密钥（内部约定，请勿外传）"),
        ("internal_sign_rule",
         'sha256("{action}|{name}|{value}|{key}")，action 取值 config / execute',
         "内部接口签名算法"),
        ("internal_api_path", "/internal/report/execute", "内部报表执行接口"),
        ("internal_config_api", "/api/report/config/save", "内部报表配置接口"),
        ("db_relative_path", "data/report.db", "数据文件相对路径"),
        ("export_temp_dir", "templates/", "报表导出缓存目录"),
        ("user_flag", user_flag, "用户层验证值（取得数据文件即可见）"),
        ("root_flag_path_decoy", "/tmp/flag.txt", "（历史遗留字段，已废弃）"),
    ]
    for key, value, note in configs:
        cur.execute("INSERT INTO sys_config (key, value, note) VALUES (?, ?, ?)",
                    (key, value, note))

    # ---- 日志表：混入诱饵 ----
    logs = [
        ("2026-01-04 09:12:31", "INFO", "调度器启动完成，worker=2"),
        ("2026-01-04 09:13:02", "INFO", "报表 sales_summary 预览任务下发成功"),
        ("2026-01-04 10:20:11", "WARN", "templates/ 目录存在历史导出文件，建议清理"),
        ("2026-01-04 11:02:44", "INFO", "内部接口调用方：scheduler-service"),
        ("2026-01-05 08:31:19", "DEBUG", "调试入口 /debug/env 仍处于开启状态，待运维关闭"),
        ("2026-01-05 09:00:00", "INFO", "备份文件 2026-01-05.tar.gz 未能上传，已在本地保留"),
        ("2026-01-05 14:22:07", "WARN", "检测到未知来源的配置查询请求，来源已忽略"),
        ("2026-01-06 02:10:00", "INFO", "root 相关文件位于容器内的独立目录，Web 账号无权访问"),
    ]
    for ts, level, msg in logs:
        cur.execute("INSERT INTO sys_log (ts, level, message) VALUES (?, ?, ?)",
                    (ts, level, msg))

    # 诱饵值：放在显眼处，误导直接寻找 flag 的人
    cur.execute(
        "INSERT INTO sys_config (key, value, note) VALUES (?, ?, ?)",
        ("legacy_flag_sample", decoy_flag, "（示例值，非有效验证值）"),
    )

    con.commit()
    con.close()

    # ---- 报表导出缓存：templates/ 下的历史导出数据文件 ----
    # 真实系统里报表导出后会把结果文件先落到缓存目录，再由预览接口读出来。
    template_dir = os.path.join(APP_ROOT, "templates")
    os.makedirs(template_dir, exist_ok=True)
    for name, title, owner, _expr in reports:
        exp_path = os.path.join(template_dir, name + ".db")
        if os.path.exists(exp_path):
            continue
        ec = sqlite3.connect(exp_path)
        ec.executescript(
            "CREATE TABLE IF NOT EXISTS export_meta (key TEXT, value TEXT);"
            "CREATE TABLE IF NOT EXISTS export_rows (id INTEGER, item TEXT, amount REAL);"
        )
        for k, v in (("report", name), ("title", title), ("owner", owner)):
            ec.execute("INSERT INTO export_meta (key, value) VALUES (?, ?)", (k, v))
        ec.execute("INSERT INTO export_meta (key, value) VALUES ('exported_at', datetime('now'))")
        for i in range(1, 6):
            ec.execute("INSERT INTO export_rows (id, item, amount) VALUES (?, ?, ?)",
                       (i, "%s-item-%d" % (name, i), round(i * 123.45, 2)))
        ec.commit()
        ec.close()
    print("[init] 已生成报表导出缓存: templates/*.db（%d 个）" % len(reports))
    print("[init] 数据库初始化完成: %s" % DB_PATH)
    print("[init] 已生成内部签名密钥（长度 %d）" % len(sign_key))
    print("[init] 已生成用户层验证值并写入系统配置表")
    print("[init] 提示：验证值不会打印到日志，请通过靶场漏洞自行获取；"
          "如需核对，可查看 data/report.db 的 sys_config 表。")


def main():
    parser = argparse.ArgumentParser(description="报表管理平台数据库初始化")
    parser.add_argument("--force", action="store_true", help="强制重建数据库")
    args = parser.parse_args()
    build_database(force=args.force)


if __name__ == "__main__":
    sys.exit(main())
