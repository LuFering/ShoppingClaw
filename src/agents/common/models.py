import logging
import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from src.config import config
from src.utils import get_docker_safe_url
from dotenv import load_dotenv
load_dotenv()


#siliconflow/Pro/deepseek-ai/DeepSeek-V3.2
def load_chat_model(fully_specified_name:str,**kwargs)->BaseChatModel:
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

    if provider in ["openai","deepseek"]:
        model_spec=f"{provider}:{model}"
        logging.debug(f"[offical]Loading model {model_spec} with kwargs {kwargs}")
        
        # 针对 DeepSeek 模型的特殊处理
        if provider == "deepseek":
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import AIMessage
            
            class DeepSeekCleanedModel(ChatOpenAI):
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
                    except Exception as e:
                        if "reasoning_content" in str(e):
                            logging.warning("[DeepSeek] reasoning_content 错误，重试...")
                            async for chunk in super()._astream(messages, *args, **kwargs):
                                yield chunk
                        else:
                            raise e

            return DeepSeekCleanedModel(
                model=model,
                api_key=api_key,
                base_url=base_url,
                stream_usage=True,
                extra_body={"enable_thinking": False}
            )

        return init_chat_model(model_spec,**kwargs)
    elif provider in["ollama"]:
        from langchain_ollama import ChatOllama



        return ChatOllama(
            model=model,
            base_url=base_url
        )
    else:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                stream_usage=True,
            )
        except Exception as e:
            raise ValueError(f"Model provider {provider} load failed:{e}")
