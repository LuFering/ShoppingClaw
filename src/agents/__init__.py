from pathlib import Path


class AgentManager():
    def __init__(self):
        self._classes = {}  # 待创建的agent
        self._instance = {}  # 已创建的agent实例

    def register_agent(self, agent_class):
        """手动注册agent"""
        self._classes[agent_class.__name__] = agent_class

    def init_all_agents(self):
        """初始化agent实例"""
        for agent in self._classes.keys():
            self.get_agent(agent)

    def get_agent(self, agent):
        """根据agent name 实例agent,载入_instance"""
        agent_class = self._classes.get(agent)
        if agent_class is None:
            return None
        self._instance[agent] = agent_class()
        return self._instance[agent]

    def get_agents(self):
        """获取所有实例化的agent"""
        return list(self._instance.values())

    async def reload_all(self):
        """异步重载所有agent"""
        #TODO:异步重载所有agent
        for agent in self._classes.keys():
            pass

    async def get_agents_info(self):
        """异步获取所有agent信息"""
        infos = []
        for agent in self._instance.values():
            info = await agent.get_info()
            infos.append(info)
        return infos

    def auto_discover_agent(self):
        """自动发现并注册 src/agents/ 下的所有智能体"""
        #agent 目录路径 ,src/agents
        agent_dir = Path(__file__).parent
        #TODO:自动发现并注册 src/agents/ 下的所有智能体
        pass

agent_manager=AgentManager()

def init_default_agents() -> None:
    from src.agents.master_agent.graph import MasterAgent

    if "MasterAgent" not in agent_manager._classes:
        agent_manager.register_agent(MasterAgent)

    if "MasterAgent" not in agent_manager._instance:
        agent_manager.init_all_agents()


def search_agent(state):
    from src.agents.search_agent import search_agent as _fn

    return _fn(state)


def analysis_agent(state):
    from src.agents.analysis_agent import analysis_agent as _fn

    return _fn(state)


def recommendation_agent(state):
    from src.agents.recommendation_agent import recommendation_agent as _fn

    return _fn(state)


init_default_agents()


__all__ = ["agent_manager", "init_default_agents", "search_agent", "analysis_agent", "recommendation_agent"]
