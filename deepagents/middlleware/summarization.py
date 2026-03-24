from typing import Any, cast

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.context_editing import TokenCounter
from langchain.agents.middleware.summarization import ContextSize, _DEFAULT_MESSAGES_TO_KEEP, DEFAULT_SUMMARY_PROMPT, \
    _DEFAULT_TRIM_TOKEN_LIMIT, SummarizationMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.prebuilt import ToolRuntime
from langgraph.runtime import Runtime
from typing_extensions import TypedDict

from deepagents.backends.protocol import BackendProtocol, BackendFactory


class TruncateArgsSettings(TypedDict, total=False):  # total来限制Typedict，无需全部修改属性
    '''长对话或复杂任务多使用该类'''
    trigger: ContextSize
    keep: ContextSize
    max_length: int  # 最长字符限制
    truncation_text: str  # 替换文本，用处不知


class SummarizationDefaults(TypedDict):
    """摘要配置模板，含3个配置"""
    trigger: ContextSize  # 触发摘要的阈值，输入类型是ContextSize【元组】("XX",值）
    keep: ContextSize  # 保留多少消息
    truncate_args_settings: TruncateArgsSettings  # 字典


def _compute_summarization_defaults(model: BaseChatModel) -> SummarizationDefaults:
    """查看模型配置(model.profile)来修改摘要配置参数"""
    has_profile = (  # 有固定模型配置的条件
            model.profile is not None
            and isinstance(model.profile, dict)
            and "max_input_tokens" in model.profile
            and isinstance(model.profile["max_input_tokens"], int)
    )

    if has_profile:
        return {
            "trigger": ("fraction", 0.85),
            "keep": ("fraction", 0.10),
            "truncate_args_settings": {
                "trigger": ("fraction", 0.85),
                "keep": ("fraction", 0.10),
            },
        }
    return {  # 若没有，返回固定摘要配置
        "trigger": ("token", 170000),
        "keep": ("message", 6),
        "truncate_args_settings": {
            "trigger": ("message", 20),
            "keep": ("message", 20),
        },
    }


class SummarizationState:
    pass


class DeepAgentsSummarizationMiddleWare(AgentMiddleware):
    state_schema = SummarizationState

    def __init__(self,
                 model: str | BaseChatModel,
                 *,
                 backend: BackendProtocol | BackendFactory,
                 trigger: ContextSize | list[ContextSize] | None = None,
                 keep: ContextSize = ("message", _DEFAULT_MESSAGES_TO_KEEP),
                 token_counter: TokenCounter = count_tokens_approximately,
                 summary_prompt: str = DEFAULT_SUMMARY_PROMPT,
                 trim_tokens_to_summarize: int | None = _DEFAULT_TRIM_TOKEN_LIMIT,
                 history_path_prefix: str = "conversation_history",
                 truncate_args_settings: TruncateArgsSettings | None = None,
                 **kwargs,
                 ) -> None:
        self._lc_helper = SummarizationMiddleware(
            model=model,
            trigger=trigger,
            keep=keep,
            token_counter=token_counter,
            summary_prompt=summary_prompt,
            trim_tokens_to_summarize=trim_tokens_to_summarize,
            **kwargs
        )

        self._backend = backend
        self._history_path_prefix = history_path_prefix

        if truncate_args_settings is None:
            self._truncate_args_trigger = None
            self._truncate_args_keep: ContextSize = ("messages", 20)
            self._max_arg_length = 2000
            self._truncation_text = "...(argument truncated)"
        else:
            self._truncate_args_trigger = None
            self._truncate_args_keep: ContextSize = ("messages", 20)
            self._max_arg_length = 2000
            self._truncation_text = "...(argument truncated)"
    @property
    def model(self) -> BaseChatModel:
        return self._lc_helper.model

    @property
    def token_counter(self)->TokenCounter:
        return self._lc_helper.token_counter

    def _get_profile_limits(self)->int|None:
        return self._lc_helper._get_profile_limits()

    def _get_backend(self,
                     state:AgentState[Any],
                     runtime:Runtime,
                     )->BackendProtocol:
        if callable(self._backend):
            config=cast("RunnableConfig",getattr(runtime,"config",{}))

            tool_runtime=ToolRuntime(
                state=state,
                context=runtime.context,
                stream_writer=runtime.stream_writer,
                store=runtime.store,
                config=config,
                tool_call_id=None
            )
            return self._backend(tool_runtime)
        return self._backend

