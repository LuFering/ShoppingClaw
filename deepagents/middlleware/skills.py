from langchain.agents.middleware import AgentMiddleware

from deepagents.backends.protocol import BackendProtocol, BackendFactory


class SkillsState:
    pass


class SkillsMiddleware(AgentMiddleware):
    state_schema = SkillsState

    def __init__(self,
                 *,
                 backend:BackendProtocol|BackendFactory,
                 sources:list[str],
                 )->None:
        self._backend=backend
        self.sources=sources
        self.system_prompt_template=" "