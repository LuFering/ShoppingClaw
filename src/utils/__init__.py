import logging
import os

logger = logging.getLogger(__name__)


def get_docker_safe_url(base_url):
    """Docker 容器环境中自动转换本地服务地址"""
    if not base_url:
        return base_url

    if os.getenv("RUNNING_IN_DOCKER")=="true":
        # 替换所有可能的本地地址形式
        base_url=base_url.replace("http://localhost", "http://host.docker.internal")
        base_url=base_url.replace("http://127.0.0.1", "http://host.docker.internal")
        logging.info(f"Running in docker, using {base_url} as base url")
    return base_url