# ============================================================================
# 报表管理平台 —— 网络安全教学靶场
# 完全自研，不使用任何闭源组件，不复刻任何商业软件实现。
# 仅限本地隔离环境学习研究使用。
# ============================================================================
FROM python:3.12-alpine

LABEL description="Report Portal - self-developed security teaching lab (local use only)"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 先装依赖，利用构建缓存
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && mkdir -p /app/data /app/templates /flag

# 应用代码
COPY app.py init_db.py entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
