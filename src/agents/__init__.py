class AgentManager():
    def __init__(self):
        self._classes = {}  # 待创建的agent
        self._instance = {}  # 已创建的agent实例

    def register_agent(self, agent_class):
        """手动注册agent"""
        self._classes[agent_class.__name__] = agent_class

    def init_all_agents(self):
        """初始化agent实例"""
        for agent in self._classes.keys()
            self.get_agent(agent)

    def get_agent(self,agent):
        """根据agent name 实例agent,载入_instance"""
        #TODO:检查是否已经创建了该 agent 的实例
        #TODO:如果仅需要重新加载 graph，则清空 graph 缓存
        agent_class=self._classes[agent]
        self._instance[agent]=agent_class()

        return self._instance[agent]

    def get_agents(self):
        """获取所有实例化的agent"""
        return list(self._instance.values())

    async def reload_all(self):
        """异步重载所有agent"""
        #TODO:异步重载所有agent
        for agent in self._classes.keys():
            pass



