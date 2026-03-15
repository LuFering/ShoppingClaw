from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.context_editing import TokenCounter
from langchain.agents.middleware.summarization import ContextSize, _DEFAULT_MESSAGES_TO_KEEP, DEFAULT_SUMMARY_PROMPT, \
    _DEFAULT_TRIM_TOKEN_LIMIT
from langchain_core.language_models import BaseChatModel
from langchain_core.messages.utils import count_tokens_approximately
from typing_extensions import TypedDict

from deepagents.backends.protocol import BackendProtocol, BackendFactory


class TruncateArgsSettings:
    pass


class SummarizationDefaults(TypedDict):
    trigger: ContextSize
    keep: ContextSize
    truncate_args_settings: TruncateArgsSettings


def _compute_summarization_defaults(model: BaseChatModel) -> SummarizationDefaults:
    pass


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
                 summary_prompt:str=DEFAULT_SUMMARY_PROMPT,
                 trim_tokens_to_summarize:int|None=_DEFAULT_TRIM_TOKEN_LIMIT,
                 history_path_prefix:str="conversation_history",
                 truncate_args_settings:TruncateArgsSettings|None=None,
                 **kwargs,
                 )->None:
        self._backend=backend
        self._history_path_prefix=history_path_prefix