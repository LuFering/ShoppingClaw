from agents.main_agent import MainAgent

_agent_instance = None


def get_agent() -> MainAgent | None:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = MainAgent()

    return _agent_instance
