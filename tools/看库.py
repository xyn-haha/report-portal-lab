# -*- coding: utf-8 -*-
# ============================================================================
#  小工具 1：查看数据文件内容
# ----------------------------------------------------------------------------
#  用途：把从靶场里拿到的数据文件打开，一次性列出所有表和数据。
#
#  用法：
#      1) 把下面 DB 改成交付给你的那份数据文件的完整路径
#      2) 在命令行执行： python 看库.py
# ============================================================================

DB = r"report.db"                      # ★★★ 只改这一行：填你下载的数据文件路径 ★★★

# ----------------------------------------------------------------------------
import os
import sqlite3

print("=" * 70)
print("数据文件:", DB)

if not os.path.exists(DB):
    print("=" * 70)
    print("!! 文件不存在。请确认路径写对了（注意盘符和目录名）。")
    print("   提示：sqlite3 打开一个不存在的路径时会静默创建一个空库，")
    print("         所以路径写错时不会报错，只会显示'没有表'。")
    raise SystemExit(1)

size = os.path.getsize(DB)
print("文件大小:", size, "字节")
print("=" * 70)

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
print("\n【表清单】", tables if tables else "（空 —— 可能是连错了文件）")

for t in tables:
    print("\n" + "-" * 70)
    print("【表】", t)
    print("-" * 70)
    cols = [d[1] for d in con.execute("PRAGMA table_info(%s)" % t)]
    print("  字段:", ", ".join(cols))
    rows = con.execute("select * from %s" % t).fetchall()
    for r in rows:
        parts = []
        for c in cols:
            v = r[c]
            s = "" if v is None else str(v)
            if len(s) > 70:
                s = s[:70] + "…"
            parts.append("%s=%s" % (c, s))
        print("   ", " | ".join(parts))
    print("   （共 %d 条）" % len(rows))

con.close()
print("\n" + "=" * 70)
print("提示：字段名里带 decoy / legacy / sample / fake 的，多半是诱饵。")
print("=" * 70)
