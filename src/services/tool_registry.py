"""
工具元数据注册表 - 参考 ScienceClaw 的 ToolRegistry

为每个工具提供图标、分类、描述等元数据，用于前端展示。
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ToolMeta:
    """工具元数据"""
    name: str
    icon: str          # emoji 图标
    category: str      # search | data | analysis | system | memory | jd_api
    description: str


class ToolRegistry:
    """
    工具元数据注册表（单例模式）
    
    前端根据 tool_meta 展示：
    - 图标 (icon): 🔍 📋 📊 等
    - 分类 (category): search, data, analysis 等
    - 描述 (description): 工具的中文说明
    """
    
    _instance = None
    _tools: Dict[str, ToolMeta] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._register_defaults()
        self._initialized = True
    
    def _register_defaults(self):
        """注册默认工具元数据"""
        defaults = {
            # ═══ 京东 API 工具 ═══
            "search_products": ToolMeta(
                "search_products", "🔍", "jd_api", "搜索商品"
            ),
            "get_product_full_detail": ToolMeta(
                "get_product_full_detail", "📋", "jd_api", "获取商品详情"
            ),
            "get_products_specs_batch": ToolMeta(
                "get_products_specs_batch", "📊", "jd_api", "批量获取规格参数"
            ),
            "filter_products_by_criteria": ToolMeta(
                "filter_products_by_criteria", "🎯", "analysis", "条件筛选商品"
            ),
            
            # ═══ 知识库工具 ═══
            "query_category_knowledge": ToolMeta(
                "query_category_knowledge", "📚", "knowledge", "查询品类知识库"
            ),
            "query_risk_policy": ToolMeta(
                "query_risk_policy", "🛡️", "risk", "查询风险策略"
            ),
            
            # ═══ 系统工具 ═══
            "write_todos": ToolMeta(
                "write_todos", "📝", "system", "任务规划/待办列表"
            ),
            "read_file": ToolMeta(
                "read_file", "📄", "filesystem", "读取文件内容"
            ),
            "edit_file": ToolMeta(
                "edit_file", "✏️", "filesystem", "编辑文件"
            ),
            "ls": ToolMeta(
                "ls", "📁", "filesystem", "列出目录内容"
            ),
            "grep": ToolMeta(
                "grep", "🔎", "filesystem", "搜索文件内容"
            ),
            
            # ═══ 网络工具 ═══
            "web_search": ToolMeta(
                "web_search", "🌐", "network", "网络搜索"
            ),
            "crawl_page": ToolMeta(
                "crawl_page", "🕷️", "network", "爬取网页"
            ),
            
            # ═══ 数据分析工具 ═══
            "analyze_data": ToolMeta(
                "analyze_data", "📈", "analysis", "数据分析"
            ),
            "compare_products": ToolMeta(
                "compare_products", "⚖️", "analysis", "商品对比"
            ),
            
            # ═══ 记忆工具 ═══
            "save_memory": ToolMeta(
                "save_memory", "💾", "memory", "保存用户偏好"
            ),
            "retrieve_memory": ToolMeta(
                "retrieve_memory", "🧠", "memory", "检索历史记忆"
            ),
        }
        self._tools.update(defaults)
    
    def get_meta(self, tool_name: str) -> ToolMeta:
        """
        获取工具元数据
        
        Args:
            tool_name: 工具名称
            
        Returns:
            ToolMeta 对象，如果未找到则返回默认元数据
        """
        return self._tools.get(
            tool_name,
            ToolMeta(tool_name, "🔧", "system", tool_name)
        )
    
    def register(self, name: str, icon: str, category: str, description: str):
        """
        注册新工具元数据
        
        Args:
            name: 工具名称
            icon: emoji 图标
            category: 分类
            description: 描述
        """
        self._tools[name] = ToolMeta(name, icon, category, description)
    
    def list_all(self) -> Dict[str, ToolMeta]:
        """列出所有已注册的工具"""
        return self._tools.copy()


# 全局单例
_tool_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """获取全局 ToolRegistry 实例"""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry
