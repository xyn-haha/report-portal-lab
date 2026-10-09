# -*- coding: utf-8 -*-
"""
报表管理平台（Report Portal）—— 网络安全教学靶场

完全自研的教学用模拟系统，用于演示一类"业务报表系统"中曾经出现过的攻击行为链：

    侦察  ->  未授权信息泄露  ->  路径遍历读取数据文件  ->  从数据文件中取得内部签名密钥
          ->  篡改持久化的业务配置字段  ->  该字段被送入表达式求值  ->  命令执行

设计要点（核心教学思想）：
    「攻击者必须先取得对某个持久化业务字段的控制权，之后该字段被不安全地求值，
      才可能触发命令执行；缺少前面任何一个前置条件，执行环节都不可能被打通。」

免责声明：
    本项目为完全自研的网络安全教学靶场，仅演示通用业务系统安全缺陷原理，
    与任何商业软件无关。不使用、不复刻任何厂商的源码、二进制、逆向逻辑、页面或内部命名。
    仅限本地隔离环境学习研究使用，禁止公网部署，禁止任何非法用途。
"""

import ast
import hashlib
import hmac
import os
import shlex
import sqlite3
import subprocess
import urllib.parse

from flask import Flask, Response, jsonify, request

# ----------------------------------------------------------------------------
# 基础路径
# ----------------------------------------------------------------------------
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "report.db")
TEMPLATE_DIR = os.path.join(APP_ROOT, "templates")

app = Flask(__name__)


# ----------------------------------------------------------------------------
# 数据访问辅助
# ----------------------------------------------------------------------------
def db_connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def cfg_get(key, default=None):
    """读取系统配置表中的一个键。"""
    try:
        con = db_connect()
        row = con.execute("SELECT value FROM sys_config WHERE key = ?", (key,)).fetchone()
        con.close()
        return row["value"] if row else default
    except Exception:
        return default


def get_report(name):
    """按名称取一条报表定义。"""
    con = db_connect()
    row = con.execute(
        "SELECT id, name, title, owner, preview_expr FROM report_def WHERE name = ?", (name,)
    ).fetchone()
    con.close()
    return row


def set_report_expr(name, expr):
    """更新报表的预览表达式字段。"""
    con = db_connect()
    cur = con.execute(
        "UPDATE report_def SET preview_expr = ?, updated_at = datetime('now') WHERE name = ?",
        (expr, name),
    )
    con.commit()
    changed = cur.rowcount
    con.close()
    return changed


# ----------------------------------------------------------------------------
# 内部签名（内部服务之间的调用凭据）
#
# 规则：sign = sha256("{action}|{name}|{value}|{key}")
#   action = config  -> 修改报表配置
#   action = execute -> 触发内部报表执行
#   key             -> 系统配置表中的内部签名密钥
# 该规则本身存放在数据文件内的系统配置表中，属于"内部约定"。
# ----------------------------------------------------------------------------
def sign_rule():
    return cfg_get("internal_sign_rule", "")


def internal_sign_key():
    return cfg_get("internal_sign_key", "")


def calc_sign(action, name, value):
    key = internal_sign_key() or ""
    raw = "%s|%s|%s|%s" % (action, name, value, key)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_sign(action, name, value):
    provided = request.headers.get("X-Internal-Sign", "") or ""
    expected = calc_sign(action, name, value)
    return hmac.compare_digest(provided.strip().lower(), expected.lower())


# ----------------------------------------------------------------------------
# 受限表达式求值（教学演示用）
#
# 这是本靶场的"最后一环"。真实系统里，业务字段被拼进表达式/模板直接求值，
# 一旦该字段可被攻击者控制，就等价于获得了执行能力。
#
# 为教学安全，这里加了简单沙盒：
#   - 只放行读取结果文件的少数命令（cat / head / ls / id / whoami）
#   - 禁止一切破坏性操作（写入、删除、下载、反弹等）
#   - 路径只能落在约定的结果目录内
# ----------------------------------------------------------------------------
# 沙盒允许读取的目录（可用环境变量 SANDBOX_READ_ROOTS 覆盖，便于跨平台本地验证）
SANDBOX_READ_ROOTS = tuple(
    os.path.realpath(os.path.abspath(x.strip()))
    for x in os.environ.get("SANDBOX_READ_ROOTS", "/flag,/root").split(",")
    if x.strip()
)
SANDBOX_ALLOWED_PROGRAMS = ("cat", "head", "ls", "id", "whoami")


def _sandbox_normalize(raw_path):
    """把用户传入的路径规范化，避免相对路径/符号链接绕过。"""
    return os.path.realpath(os.path.abspath(str(raw_path)))


def _sandbox_path_allowed(raw_path):
    """判断目标路径是否落在允许读取的目录内。"""
    target = _sandbox_normalize(raw_path)
    for root in SANDBOX_READ_ROOTS:
        if target == root or target.startswith(root + os.sep):
            return True
    return False


def sandbox_run(cmd):
    """受限命令执行：仅允许读取结果文件，禁止破坏性操作。"""
    try:
        parts = shlex.split(str(cmd))
    except ValueError as err:
        return "命令解析失败: %s" % err
    if not parts:
        return "空命令"

    prog = os.path.basename(parts[0])
    if prog not in SANDBOX_ALLOWED_PROGRAMS:
        return "沙盒已阻止该命令: %s（本环境仅允许读取结果文件）" % prog

    for arg in parts[1:]:
        if arg.startswith("-"):
            continue
        if not _sandbox_path_allowed(arg):
            return "沙盒已阻止访问该路径: %s" % arg

    if prog in ("ls",) and len(parts) == 1:
        parts = parts + ["/flag"]

    try:
        proc = subprocess.run(parts, capture_output=True, timeout=5, shell=False)
    except Exception as err:
        return "执行异常: %r" % err

    out = (proc.stdout or b"").decode("utf-8", "replace")
    err = (proc.stderr or b"").decode("utf-8", "replace")
    return out if out.strip() else (err.strip() or "（无输出）")


def sandbox_read_file(path):
    """受限文件读取：只能读结果目录内的文件。"""
    if not _sandbox_path_allowed(path):
        return "沙盒已阻止访问该路径: %s" % path
    try:
        with open(_sandbox_normalize(path), "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception as err:
        return "读取失败: %r" % err


def report_total(report_name):
    """
    业务表达式示例函数：返回某报表的汇总结果（教学用占位实现）。
    正常业务配置里，报表的预览表达式就是调用它。
    """
    try:
        con = db_connect()
        row = con.execute(
            "SELECT COUNT(*) AS c FROM report_def WHERE name = ?", (str(report_name),)
        ).fetchone()
        con.close()
        return {"report": str(report_name), "rows": row["c"] if row else 0}
    except Exception as err:
        return "汇总失败: %r" % err


# 表达式可用的白名单函数
SAFE_FUNCS = {
    "report_total": report_total,
    "run": sandbox_run,
    "read_file": sandbox_read_file,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
}

_ALLOWED_AST_NODES = (
    ast.Expression, ast.Constant, ast.Name, ast.Load, ast.Call, ast.keyword,
    ast.Tuple, ast.List, ast.Dict, ast.BinOp, ast.Add, ast.Sub, ast.Mult,
    ast.Div, ast.Mod, ast.USub, ast.UAdd, ast.Compare, ast.Eq, ast.NotEq,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not, ast.IfExp,
)


def evaluate_expression(expr):
    """对业务字段执行表达式求值（带简单沙盒与语法白名单）。"""
    if expr is None:
        return "（空表达式）"
    expr = str(expr)
    if len(expr) > 2000:
        return "表达式过长"

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as err:
        return "表达式语法错误: %s" % err

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST_NODES):
            return "表达式包含不被允许的语法: %s" % type(node).__name__
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return "表达式包含不被允许的名称"

    try:
        return eval(compile(tree, "<report_expr>", "eval"),
                    {"__builtins__": {}}, dict(SAFE_FUNCS))
    except Exception as err:
        return "表达式求值异常: %s: %s" % (type(err).__name__, err)


# ----------------------------------------------------------------------------
# 页面：首页
# ----------------------------------------------------------------------------
HOME_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>报表管理平台</title>
  <style>
    body{font-family:system-ui,"Microsoft YaHei",sans-serif;margin:40px;color:#222}
    h1{font-size:22px}
    .box{border:1px solid #ddd;padding:16px;max-width:760px;border-radius:6px}
    li{margin:6px 0}
    .muted{color:#888;font-size:13px}
  </style>
</head>
<body>
  <h1>报表管理平台 · 控制台</h1>
  <div class="box">
    <p>欢迎使用报表管理平台。当前版本支持：报表预览、报表配置、内部调度。</p>

    <h3 style="font-size:16px;margin:18px 0 8px">报表数据预览</h3>
    <label>选择报表：</label>
    <select id="reportSelect">
      <option value="sales_summary">销售汇总月报</option>
      <option value="inventory_snapshot">库存快照日报</option>
      <option value="finance_monthly">财务月结报表</option>
      <option value="ops_health">运维健康巡检</option>
    </select>
    <button onclick="previewReport()">预览</button>

    <p class="muted" style="margin-top:14px">
      其他入口：报表配置 /api/report/config/save ｜ 控制台登录 /login ｜
      <a href="/help/expression">表达式语法说明</a>
    </p>
    <p class="muted">系统状态：正常　|　调度器：运行中</p>
  </div>

  <script>
  // 报表预览：把选中的报表对应的"导出数据文件"交给后端读取
  function previewReport() {
    var name = document.getElementById('reportSelect').value;
    var file = name + '.db';          // 导出文件与报表同名
    window.location.href = '/report/preview?name=' + encodeURIComponent(file);
  }
  </script>

  <!--
    TODO(运维) 上线前处理：
      1. /debug/env 是部署期临时加的排查入口，正式环境记得关掉；
      2. data 目录不要再往里塞临时导出文件；
      3. /internal/report/execute 的调用方只有调度器，不要对外暴露。
  -->

</body>
</html>
"""


@app.route("/")
def index():
    return Response(HOME_PAGE, mimetype="text/html; charset=utf-8")


@app.route("/login", methods=["GET", "POST"])
def login():
    """控制台登录。系统初始化后没有任何可用的默认账号。"""
    if request.method == "POST":
        return jsonify(success=False, msg="用户名或密码错误（系统未开通默认账号）"), 401
    return Response(
        "<!DOCTYPE html><html lang='zh-CN'><meta charset='utf-8'>"
        "<title>控制台登录</title><body style='font-family:sans-serif;margin:40px'>"
        "<h1>控制台登录</h1>"
        "<form method='post'><input name='username' placeholder='用户名'> "
        "<input name='password' type='password' placeholder='密码'> "
        "<button>登录</button></form>"
        "<p style='color:#888'>提示：系统未开通默认账号，请联系管理员分配。</p>"
        "</body></html>",
        mimetype="text/html; charset=utf-8",
    )


# ----------------------------------------------------------------------------
# 第 2 环：未授权信息泄露（部署期遗留的排查入口）
# ----------------------------------------------------------------------------
@app.route("/debug/env")
def debug_env():
    """
    部署排查入口，未做鉴权。
    会泄露：运行环境信息、数据文件位置、内部接口名称、调用约定提示。
    """
    return jsonify(
        app="report-portal",
        version="1.4.2",
        debug=True,
        app_home="/app",
        data_dir="data",
        database="data/report.db",
        temp_dir="templates/",
        internal_api="/internal/report/execute",
        internal_config_api="/api/report/config/save",
        internal_auth="内部接口需携带请求头 X-Internal-Sign",
        note="内部签名规则随系统配置一起存放，请勿外传",
    )


# ----------------------------------------------------------------------------
# 第 3 环：带过滤的路径遍历（可被双重编码绕过）
#
# 过滤逻辑只看请求里"原样"的字符串，但取文件前又做了一次解码，
# 于是对 ../ 做双重 URL 编码即可绕过；同时限制只能读到应用目录内的数据文件。
# ----------------------------------------------------------------------------
@app.route("/report/preview")
def report_preview():
    raw = request.args.get("name", "")

    # 明文过滤
    if "../" in raw or "..\\" in raw or raw.startswith("/"):
        return jsonify(success=False, msg="文件名不合法"), 400

    # 历史兼容处理：对参数再做一次解码
    filename = urllib.parse.unquote(raw)

    target = os.path.realpath(os.path.join(TEMPLATE_DIR, filename))
    app_root = os.path.realpath(APP_ROOT)

    # 只允许预览应用目录内的数据文件
    if not target.startswith(app_root + os.sep):
        return jsonify(success=False, msg="仅允许预览应用目录内的数据文件"), 403
    if not target.endswith(".db"):
        return jsonify(success=False, msg="仅允许预览报表数据文件（.db）"), 403
    if not os.path.isfile(target):
        return jsonify(success=False, msg="报表数据文件不存在"), 404

    with open(target, "rb") as fh:
        payload = fh.read()

    resp = Response(payload, mimetype="application/octet-stream")
    resp.headers["Content-Disposition"] = 'attachment; filename="%s"' % os.path.basename(target)
    return resp


@app.route("/report/list")
def report_list():
    """报表清单（公开信息）。"""
    con = db_connect()
    rows = con.execute("SELECT name, title, owner FROM report_def ORDER BY id").fetchall()
    con.close()
    return jsonify(success=True, data=[dict(r) for r in rows])


# ----------------------------------------------------------------------------
# 第 4 环：修改持久化业务配置（需要伪造内部签名）
# ----------------------------------------------------------------------------
@app.route("/api/report/config/save", methods=["POST"])
def report_config_save():
    """
    更新报表定义。调用方约定为内部管理端，必须携带 X-Internal-Sign。
    签名规则：sha256("config|{name}|{value}|{key}")
    """
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", ""))
    value = str(body.get("value", ""))

    if not name:
        return jsonify(success=False, msg="缺少参数 name"), 400

    if not internal_sign_key():
        return jsonify(success=False, msg="内部服务尚未初始化"), 500

    if not check_sign("config", name, value):
        return jsonify(success=False, msg="内部签名校验失败"), 403

    if get_report(name) is None:
        return jsonify(success=False, msg="报表不存在"), 404

    changed = set_report_expr(name, value)
    return jsonify(success=True, msg="报表配置已更新", affected=changed)


# ----------------------------------------------------------------------------
# 第 5 环：内部报表执行（条件触发点）
#
# 只有当前置条件全部满足时才会真正产生效果：
#   1) 拿到内部签名密钥（否则签名校验直接 403）
#   2) 借助签名把报表的 preview_expr 字段改成攻击者想要的内容
#   3) 再带签名调用本接口，后端才会把该字段送进表达式求值
# 任何一步缺失，都无法走到求值环节。
# ----------------------------------------------------------------------------
@app.route("/internal/report/execute", methods=["POST"])
def internal_report_execute():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", ""))

    if not internal_sign_key():
        return jsonify(success=False, msg="内部服务尚未初始化"), 500

    if not check_sign("execute", name, ""):
        return jsonify(success=False, msg="内部签名校验失败"), 403

    row = get_report(name)
    if row is None:
        return jsonify(success=False, msg="报表不存在"), 404

    expr = row["preview_expr"]
    app.logger.warning("执行报表 %s 的预览表达式", name)

    result = evaluate_expression(expr)
    return jsonify(success=True, report=name, expression=expr, result=result)


# ----------------------------------------------------------------------------
# 帮助页：报表预览表达式语法说明
# （真实报表系统通常会提供这类"表达式/公式语法"帮助文档）
# ----------------------------------------------------------------------------
EXPR_HELP_PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>表达式语法说明</title>
<style>body{font-family:system-ui,"Microsoft YaHei",sans-serif;margin:40px;max-width:820px;color:#222}
code{background:#f4f4f4;padding:2px 5px;border-radius:3px}
table{border-collapse:collapse;margin:12px 0}td,th{border:1px solid #ddd;padding:6px 10px;text-align:left}
.warn{color:#b00}</style></head><body>
<h1>报表预览表达式 · 语法说明</h1>
<p>报表的"预览表达式"字段会在报表执行时被求值，用于计算预览结果。可用函数如下：</p>
<table>
  <tr><th>函数</th><th>说明</th></tr>
  <tr><td><code>report_total(name)</code></td><td>返回指定报表的汇总结果（正常业务表达式使用）</td></tr>
  <tr><td><code>run(cmd)</code></td><td>在服务器上执行命令并返回输出结果</td></tr>
  <tr><td><code>read_file(path)</code></td><td>读取文件内容并返回</td></tr>
</table>
<p>通用函数：<code>len str int float bool list dict min max sum abs round</code></p>
<p><b>结果目录</b>（表达式仅可读取以下目录内的文件）：</p>
<ul><li><code>/flag</code></li><li><code>/root</code></li></ul>
<p class="warn">注意：生产环境对求值环境启用了沙箱限制，禁用的操作会直接返回拒绝信息。</p>
</body></html>
"""


@app.route("/help/expression")
def help_expression():
    """表达式语法说明页（公开帮助文档）。"""
    return Response(EXPR_HELP_PAGE, mimetype="text/html; charset=utf-8")


# ----------------------------------------------------------------------------
# 诱饵：看起来像命令执行入口，实际永远拒绝
# ----------------------------------------------------------------------------
@app.route("/internal/debug/exec", methods=["POST", "GET"])
def decoy_debug_exec():
    return jsonify(success=False, msg="该入口已于 v1.3 下线，请使用调度器接口"), 403


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    # 监听端口可通过环境变量 PORT 覆盖，默认 8080
    listen_port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=listen_port, debug=False)
