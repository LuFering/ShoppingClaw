import logging
import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from src.config import config
from src.utils import get_docker_safe_url


#siliconflow/Pro/deepseek-ai/DeepSeek-V3.2
def load_chat_model(fully_specified_name:str,**kwargs)->BaseChatModel:
    """加载chat model"""
    provider,model=fully_specified_name.split("/",maxsplit=1)

    model_info=config.model_name.get(provider)
    logging.info(f">>>进入[load_chat_model]")
    logging.info(f"provider:{provider},model:{model},model_info:{model_info}")
    if not model_info:
        raise ValueError(f"Unknown model provider:{provider}")

    #  env_var=model_info.env
    #
    #  api_key=os.getenv(env_var) or env_var
    #
    base_url=get_docker_safe_url(model_info.base_url)

    if provider in ["openai","deepseek"]:
        model_spec=f"{provider}:{model}"
        logging.debug(f"[offical]Loading model {model_spec} with kwargs {kwargs}")
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
                # api_key=SecretStr(api_key),
                # base_url=base_url,
                stream_usage=True,
            )
        except Exception as e:
            raise ValueError(f"Model provider {provider} load failed:{e}")