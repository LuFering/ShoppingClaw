from typing import NotRequired, Annotated

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import PrivateStateAttr, AgentState, ResponseT
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolRuntime
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from zstandard import backend

from deepagents.backends.protocol import BackendProtocol, BackendFactory


class SkillMetadata:
    pass


class SkillsState(AgentState):
    skill_metadata: NotRequired[Annotated[list[SkillMetadata], PrivateStateAttr]]


class SkillsStateUpdate:
    pass


def _list_skills(backend, source_path):
    pass


class SkillsMiddleware(AgentMiddleware[SkillsState, ContextT, ResponseT]):
    state_schema = SkillsState

    def __init__(self,
                 *,
                 backend: BackendProtocol | BackendFactory,
                 sources: list[str],
                 ) -> None:
        self._backend = backend
        self.sources = sources
        self.system_prompt_template = " "

    def _get_backend(self,
                     state: SkillsState,
                     runtime: Runtime,
                     config: RunnableConfig,
                     ) -> BackendProtocol:
        if callable(self._backend):
            tool_runtime = ToolRuntime(
                state=state,
                context=runtime.context,
                stream_writer=runtime.stream_writer,
                store=runtime.store,
                config=config,
                tool_call_id=None,
            )
            backend = self._backend(tool_runtime)
            return backend

        return self._backend
    
    def before_agent(self, state: SkillsState, runtime: Runtime, config: RunnableConfig) -> SkillsStateUpdate | None:  # ty: ignore[invalid-method-override]

        # Skip if skills_metadata is already present in state (even if empty)
        if "skills_metadata" in state:
            return None

        # Resolve backend (supports both direct instances and factory functions)
        backend = self._get_backend(state, runtime, config)
        all_skills: dict[str, SkillMetadata] = {}

        # Load skills from each source in order
        # Later sources override earlier ones (last one wins)
        for source_path in self.sources:
            source_skills = _list_skills(backend, source_path)
            for skill in source_skills:
                all_skills[skill["name"]] = skill

        skills = list(all_skills.values())
        return SkillsStateUpdate(skills_metadata=skills)
