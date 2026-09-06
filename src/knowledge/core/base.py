from abc import ABC, abstractmethod

from src.knowledge.core.models import KnowledgeItem


class RetrieverBase(ABC):
    """检索器抽象基类
    
    定义统一的检索接口，所有存储后端（VectorStore/RuleEngine/FAQStore）需实现此接口。
    """

    @abstractmethod
    async def retrieve(
            self,
            query: str,
            category: str | None = None,
            top_k: int = 5,
    ) -> list[KnowledgeItem]:
        """执行知识检索
        
        Args:
            query: 查询文本
            category: 商品类目过滤（如"手机"），可选
            top_k: 返回结果数量上限
            
        Returns:
            检索到的知识项列表，按相关性或优先级排序
        """
        ...

    @abstractmethod
    async def add(self, items: list[KnowledgeItem]) -> None:
        """添加知识项到存储
        
        Args:
            items: 待添加的知识项列表
        """
        ...

    @abstractmethod
    async def delete_by_doc_id(self, doc_id: str) -> None:
        """按文档 ID 删除所有相关分块（删旧建新策略）
        
        Args:
            doc_id: 来源文档 ID
        """
        ...