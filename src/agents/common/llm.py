import asyncio
import logging
import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from src.config import config
from src.utils import get_docker_safe_url
from dotenv import load_dotenv
load_dotenv()


# 模型实例缓存，避免同一模型被重复加载
# 会返回 reasoning_content 的 OpenAI 兼容 provider（均启用 reasoning 感知封装）
REASONING_AWARE_PROVIDERS = ("deepseek", "aliyun", "SenseNova", "openai")
_model_cache: dict[str, BaseChatModel] = {}

# ═══════════════════════════════════════════════════════════════════════════
# 限额熔断（circuit breaker）
#
# 背景：上层（前端模型选择器）会把用户选中的 "provider/model" 随请求传下来，
# 一旦该模型配额用尽（429 insufficient_quota / tpm/rpm 超限）或欠费（402），
# 整条 SSE 流会直接在第一次 model 调用处抛错，前端只会看到一句问候语，
# 所有工具卡 / 编排卡 / 子智能体卡统统不出现 —— 表现为"前端设计丢了"，
# 实际是模型压根没跑起来。
#
# 对策：把「已经确认不可用」的模型记进一个带 TTL 的黑名单，加载时直接跳过它，
# 静默回退到默认模型（config.default_model）。这样即使前端 localStorage 里
# 存着一个欠费的模型名，对话也能正常跑完并出卡片。
# ═══════════════════════════════════════════════════════════════════════════
_UNAVAILABLE_TTL_SECONDS = 600  # 10 分钟内不再重试同一个死模型
_unavailable_models: dict[str, float] = {}
_UNAVAILABLE_MARKERS = (
    "insufficient_quota",
    "insufficient balance",
    "inference exceeds tpm/rpm limit",
    "free quota exhausted",
    "rate limit",
    "429003",
    # deepseek 官方 402 只有一句 "Insufficient Balance"
)


def mark_model_unavailable(fully_specified_name: str, reason: str = "") -> None:
    """把一个模型标记为「暂时不可用」，在 TTL 内加载时会被跳过。"""
    import time as _time

    if not fully_specified_name:
        return
    first = fully_specified_name not in _unavailable_models
    _unavailable_models[fully_specified_name] = _time.time() + _UNAVAILABLE_TTL_SECONDS
    if first:
        logging.warning(
            f"[ModelHealth] 模型 {fully_specified_name} 已标记为不可用 "
            f"({_UNAVAILABLE_TTL_SECONDS}s 内跳过)：{reason}"
        )


def is_model_unavailable(fully_specified_name: str) -> bool:
    """判断模型是否仍在熔断窗口内。窗口过期会自动清除。"""
    import time as _time

    exp = _unavailable_models.get(fully_specified_name)
    if exp is None:
        return False
    if _time.time() >= exp:
        _unavailable_models.pop(fully_specified_name, None)
        logging.info(f"[ModelHealth] 模型 {fully_specified_name} 熔断窗口已过期，恢复可用")
        return False
    return True


def is_quota_error(exc: BaseException) -> bool:
    """判断异常是否属于「这个模型不能用了」这一类（配额/欠费/限流）。"""
    text = f"{type(exc).__name__}: {exc}".lower()
    if "ratelimiterror" in text or "apistatuserror" in text:
        return True
    return any(m in text for m in _UNAVAILABLE_MARKERS)


def load_chat_model_with_fallback(fully_specified_name: str):
    """加载模型；若该模型已被熔断，则回退到 config.default_model。

    返回 (model_instance, actual_spec_used)。
    """
    if fully_specified_name and is_model_unavailable(fully_specified_name):
        fallback = config.default_model
        if fallback != fully_specified_name:
            logging.warning(
                f"[ModelHealth] {fully_specified_name} 处于熔断窗口，"
                f"本次对话改用默认模型 {fallback}"
            )
            return load_chat_model(fallback), fallback
    return load_chat_model(fully_specified_name), fully_specified_name


def load_chat_model(fully_specified_name:str,**kwargs)->BaseChatModel:
    # 检查缓存：相同模型名 + 相同 kwargs 直接复用
    cache_key = f"{fully_specified_name}__{hash(frozenset(kwargs.items()))}" if kwargs else fully_specified_name
    if cache_key in _model_cache:
        logging.debug(f"[load_chat_model] cache hit: {fully_specified_name}")
        return _model_cache[cache_key]
    """加载chat model"""
    provider,model=fully_specified_name.split("/",maxsplit=1)

    model_info=config.model_name.get(provider)
    logging.info(f">>>进入[load_chat_model]")
    logging.info(f"provider:{provider},model:{model},model_info:{model_info}")
    if not model_info:
        raise ValueError(f"Unknown model provider:{provider}")

    env_var=model_info.env
    #
    api_key=os.getenv(env_var) or env_var
    #
    base_url=get_docker_safe_url(model_info.base_url)
    logging.debug(f"api_key:{api_key[:10]}... (hidden)")

    if provider in ["openai","deepseek","aliyun","SenseNova"]:
        model_spec=f"{provider}:{model}"
        logging.debug(f"[offical]Loading model {model_spec} with kwargs {kwargs}")
        
        # 针对会返回 reasoning_content 的 provider 的处理（不止 DeepSeek）
        if provider in REASONING_AWARE_PROVIDERS:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import AIMessage
            
            class ReasoningAwareChatOpenAI(ChatOpenAI):
                """自动处理 reasoning_content 的 DeepSeek 模型包装类"""

                def _get_request_payload(self, input_, *, stop=None, **kwargs):
                    """
                    重写：提取 AIMessage.additional_kwargs 中的 reasoning_content，
                    待 LangChain 完成消息转换后，注入到请求 dict 的顶层。
                    _convert_message_to_dict 会丢弃 additional_kwargs，
                    所以必须在转换前提取、转换后注入。
                    """
                    # 1. 转换前：从原始消息中提取 reasoning_content
                    messages = self._convert_input(input_).to_messages()
                    reasoning_map = {}  # index -> reasoning_content
                    for i, msg in enumerate(messages):
                        if isinstance(msg, AIMessage):
                            rc = msg.additional_kwargs.get("reasoning_content")
                            if rc:
                                reasoning_map[i] = rc

                    # 2. 转换：让 LangChain 把消息转为 dict（会丢弃 additional_kwargs）
                    payload = super()._get_request_payload(input_, stop=stop, **kwargs)

                    # 3. 转换后：将 reasoning_content 注入到对应 assistant 消息的顶层 dict
                    if reasoning_map:
                        payload_messages = payload.get("messages", [])
                        for i, rc in reasoning_map.items():
                            if i < len(payload_messages) and payload_messages[i].get("role") == "assistant":
                                payload_messages[i]["reasoning_content"] = rc
                                logging.debug(
                                    f"[DeepSeek] 注入 reasoning_content 到消息 #{i} "
                                    f"({len(rc)} chars)"
                                )

                    return payload

                def _create_chat_result(self, response, generation_info=None):
                    """重写：从非流式响应中捕获 reasoning_content"""
                    response_dict = (
                        response
                        if isinstance(response, dict)
                        else response.model_dump(
                            exclude={"choices": {"__all__": {"message": {"parsed"}}}}
                        )
                    )
                    reasoning_contents = []
                    for choice in response_dict.get("choices", []):
                        rc = choice.get("message", {}).get("reasoning_content")
                        reasoning_contents.append(rc)

                    result = super()._create_chat_result(response, generation_info)

                    for i, gen in enumerate(result.generations):
                        if i < len(reasoning_contents) and reasoning_contents[i]:
                            if isinstance(gen.message, AIMessage):
                                gen.message.additional_kwargs.setdefault(
                                    "reasoning_content", reasoning_contents[i]
                                )
                                logging.debug(
                                    "[DeepSeek] 非流式响应捕获 reasoning_content: "
                                    f"{len(reasoning_contents[i])} chars"
                                )
                    return result

                def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
                    """重写：从流式 chunk 中捕获 reasoning_content"""
                    reasoning_content = None
                    choices = chunk.get("choices", [])
                    if choices and isinstance(choices[0].get("delta"), dict):
                        rc = choices[0]["delta"].get("reasoning_content")
                        if rc:
                            reasoning_content = rc

                    generation_chunk = super()._convert_chunk_to_generation_chunk(
                        chunk, default_chunk_class, base_generation_info
                    )

                    if reasoning_content and generation_chunk and hasattr(generation_chunk.message, 'additional_kwargs'):
                        generation_chunk.message.additional_kwargs["reasoning_content"] = reasoning_content

                    return generation_chunk

                async def _astream(self, messages, *args, **kwargs):
                    try:
                        async for chunk in super()._astream(messages, *args, **kwargs):
                            yield chunk
                    except asyncio.CancelledError:
                        # 客户端断开 — 阻止 httpx 在清理时打 decode_complete 错误到 stderr
                        logging.debug("[DeepSeek] stream cancelled during _astream")
                        raise
                    except Exception as e:
                        if "reasoning_content" in str(e):
                            logging.warning("[DeepSeek] reasoning_content 错误，重试...")
                            async for chunk in super()._astream(messages, *args, **kwargs):
                                yield chunk
                        else:
                            logging.warning(f"[DeepSeek] streaming error: {type(e).__name__}: {e}")
                            raise

            # enable_thinking 是 DeepSeek 专有字段；其他 provider 传了会 400
            _ctor_kwargs = {
                "model": model,
                "api_key": api_key,
                "base_url": base_url,
                "stream_usage": True,
                "max_tokens": 8192,
            }
            if provider == "deepseek":
                _ctor_kwargs["extra_body"] = {"enable_thinking": True}
            model_instance = ReasoningAwareChatOpenAI(**_ctor_kwargs)
            _model_cache[cache_key] = model_instance
            return model_instance

        model_instance = init_chat_model(model_spec, **kwargs)
        _model_cache[cache_key] = model_instance
        return model_instance
    elif provider in["ollama"]:
        from langchain_ollama import ChatOllama

        model_instance = ChatOllama(
            model=model,
            base_url=base_url
        )
        _model_cache[cache_key] = model_instance
        return model_instance
    else:
        try:
            from langchain_openai import ChatOpenAI
            model_instance = ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                stream_usage=True,
            )
            _model_cache[cache_key] = model_instance
            return model_instance
        except Exception as e:
            raise ValueError(f"Model provider {provider} load failed:{e}")
