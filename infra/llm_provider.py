"""
LLM 提供者 - 大语言模型接口
"""


class LLMProvider:
    """LLM 提供者类"""
    
    def __init__(self, api_key: str = None, model: str = "gpt-3.5-turbo"):
        """
        初始化 LLM 提供者
        
        Args:
            api_key: API 密钥
            model: 模型名称
        """
        pass
    
    async def generate_text(self, prompt: str) -> str:
        """
        生成文本
        
        Args:
            prompt: 输入提示
            
        Returns:
            生成的文本
        """
        # TODO: 实现文本生成逻辑
        pass
    
    async def chat(self, messages: list) -> str:
        """
        对话
        
        Args:
            messages: 消息列表
            
        Returns:
            回复消息
        """
        # TODO: 实现对话逻辑
        pass
