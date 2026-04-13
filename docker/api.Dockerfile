# 使用轻量级Python基础镜像
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/

# 设置工作目录
WORKDIR /app

# 环境变量设置
ENV TZ=Asia/Shanghai \
    UV_COMPILE_BYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    RUNNING_IN_DOCKER=true

# 设置代理和时区,更换镜像源,安装系统依赖 - 合并为一个RUN减少层数
RUN set -ex \
    # (A) 设置时区
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    # (B) 替换清华源 (针对 Debian Bookworm 的新版格式)
    && sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|security.debian.org/debian-security|mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources \
    # (C) 安装必要的系统库
    && apt-get update \
    && apt-get install -y --no-install-recommends --fix-missing \
        curl \
        libpq5 \
    # (D) 清理垃圾,减小体积
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制项目配置文件
COPY pyproject.toml /app/pyproject.toml
COPY .python-version /app/.python-version
COPY uv.lock /app/uv.lock

# 安装依赖(使用清华源加速)
# 注意：从 pyproject.toml 提取依赖并写入临时文件，然后安装
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv && python3 -c "import tomllib; data = tomllib.load(open('pyproject.toml', 'rb')); open('/tmp/requirements.txt', 'w').write('\n'.join(data['project']['dependencies']))" && uv pip install -r /tmp/requirements.txt

# 激活虚拟环境并添加到PATH
ENV PATH="/app/.venv/bin:$PATH"

# 复制代码到容器中
COPY src/ /app/src/
COPY server/ /app/server/
COPY agents/ /app/agents/
COPY deepagents/ /app/deepagents/