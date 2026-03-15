from typing import TypedDict, NotRequired, Sequence, Callable, Any

from langchain.agents.middleware import AgentMiddleware, InterruptOnConfig
from langchain.agents.middleware.types import ResponseT
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.typing import ContextT

from deepagents.backends.protocol import BackendFactory, BackendProtocol


class SubAgent(TypedDict):
    name: str
    description: str
    system_prompt: str
    tools: NotRequired[Sequence[BaseTool | Callable | dict[str, Any]]]
    model: NotRequired[str | BaseChatModel]
    middleware: NotRequired[list[AgentMiddleware]]
    interrupt_on: NotRequired[dict[str, bool | InterruptOnConfig]]
    skills: NotRequired[list[str]]


GENERAL_PURPOSE_SUBAGENT: SubAgent = {
    "name": "general-purpose",
    "description": "",
    "system_prompt": "",
}


class CompiledSubAgent(TypedDict):
    name: str
    description: str
    runnable: Runnable


def _build_task_tool(subagent_specs, task_description):
    pass


class SubAgentMiddleware(AgentMiddleware[Any, ContextT, ResponseT]):
    def __init__(self,
                 *,
                 backend: BackendFactory | BackendProtocol | None = None,
                 subagents: list[SubAgent | CompiledSubAgent] | None = None,
                 system_prompt: str | None = None,
                 task_description: str | None = None,
                 **kwargs,
                 ) -> None:
        super().__init__()  # 因为AgentMiddleware没有构建__init__方法，所以此方法没有继承任何东西
        self._backend = backend
        self._subagents = subagents
        subagent_specs = self._get_subagents()
        task_tool = _build_task_tool(subagent_specs, task_description)
        if system_prompt and subagent_specs:
            agents_decs="\n".join(f"-{s['name']}:{s['description']}"for s in subagent_specs)
            self.system_prompt=system_prompt+"\n\n Available subagent types:\n"+agents_decs
        else:
            self.system_prompt=system_prompt
        self.tools=[task_tool]
    def _get_subagents(self):
        pass
