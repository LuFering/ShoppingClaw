"""证据收集中间件"""
import json
import re
import logging
from datetime import datetime
from typing import NotRequired, Annotated
from langchain.agents.middleware.types import AgentMiddleware, AgentState, PrivateStateAttr
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime

# 导入 Schema 用于强制校验
try:
    from agents.common.model import ResearcherOutput, AnalystOutput, CriticOutput, MemoryOutput
except ImportError:
    ResearcherOutput = AnalystOutput = CriticOutput = MemoryOutput = None


class EvidenceCollectorState(AgentState):
    """证据收集状态字段"""
    evidence: NotRequired[Annotated[dict, PrivateStateAttr]]


class EvidenceCollectorMiddleware(AgentMiddleware):
    """证据收集中间件
    
    在after_model阶段解析ToolMessage中的SubAgent输出，
    写入state对应字段
    """
    
    name = "evidence_collector"
    state_schema = EvidenceCollectorState
    
    def after_model(self, state: dict, runtime: Runtime) -> dict | None:
        """同步版"""
        return self._collect_evidence(state)
    
    async def aafter_model(self, state: dict, runtime: Runtime) -> dict | None:
        """异步版"""
        return self._collect_evidence(state)
    
    def _extract_json_from_content(self, content: str) -> dict | None:
        """从可能包含 Markdown 或额外文本的内容中提取 JSON"""
        if isinstance(content, dict):
            return content
        
        # 1. 尝试直接解析
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 2. 尝试提取 ```json ... ``` 块
        match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 3. 尝试提取第一个 { ... } 块
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
                
        return None

    def _infer_evidence_type(self, content_dict: dict) -> str | None:
        """根据 JSON 内容结构推断 evidence_type（兼容没有 evidence_type 字段的旧输出）。"""
        data = content_dict.get("data")
        if not data or not isinstance(data, dict):
            return None
        if "products" in data:
            return "product_list"
        if any(k in data for k in ("analysis_mode", "key_decision_factors", "dimension_scores")):
            return "comparison_matrix"
        if "risks" in data:
            return "risk_report"
        if any(k in data for k in ("relevant_preferences", "new_signals", "preference_insights")):
            return "user_preference"
        return None

    def _collect_evidence(self, state: dict) -> dict | None:
        """收集证据并进行 Pydantic 校验"""
        messages = state.get("messages", [])

        # 找到所有 ToolMessage（支持并行 SubAgent 场景）
        tool_messages = [msg for msg in messages if isinstance(msg, ToolMessage)]

        if not tool_messages:
            return None

        # 映射关系
        mapping = {
            "product_list": ("research_data", ResearcherOutput),
            "comparison_matrix": ("analysis_report", AnalystOutput),
            "risk_report": ("risk_audit", CriticOutput),
            "user_preference": ("user_profile", MemoryOutput)
        }

        # 汇总更新
        merged_update: dict = {}
        merged_evidence = dict(state.get("evidence") or {})

        for last_tool_msg in tool_messages:
            # 智能提取 JSON
            raw_content = last_tool_msg.content
            content_dict = self._extract_json_from_content(raw_content)

            if not content_dict:
                continue

            evidence_type = content_dict.get("evidence_type")

            # 如果没有 evidence_type，尝试从结构推断
            if not evidence_type:
                evidence_type = self._infer_evidence_type(content_dict)

            if not evidence_type:
                continue

            target_info = mapping.get(evidence_type)
            if not target_info:
                continue

            target_field, schema_class = target_info

            # Pydantic 强制校验与清洗
            validated_data = content_dict.get("data")
            if schema_class and evidence_type in content_dict:
                try:
                    validated_output = schema_class.model_validate(content_dict)
                    validated_data = validated_output.data.model_dump(exclude_none=True, mode='json')
                    logging.info(f"[EvidenceCollector] Pydantic 校验成功: {evidence_type}")
                except Exception as e:
                    logging.error(f"[EvidenceCollector] Pydantic 校验失败 ({evidence_type}): {str(e)}")
                    validated_data = content_dict.get("data")

            # 打印输出摘要（用于调试防幻觉效果）
            if evidence_type == "product_list" and validated_data:
                products = validated_data.get("products", [])
                logging.info(f"[Researcher Output] 收到 {len(products)} 款商品")
                for p in products[:2]:
                    logging.info(f"  - ID: {p.get('id')}, Title: {str(p.get('title'))[:30]}..., Price: {p.get('price')}")

            # 写入更新
            merged_update[target_field] = validated_data
            merged_evidence[target_field] = validated_data
            merged_update.setdefault("evidence_log", []).append({
                "type": evidence_type,
                "source": last_tool_msg.name or "unknown",
                "content": content_dict.get("summary", ""),
                "timestamp": datetime.now().isoformat()
            })

            logging.info(f"[EvidenceCollector] 收集完成: {evidence_type} -> {target_field}")

        if merged_evidence:
            merged_update["evidence"] = merged_evidence

        return merged_update if merged_update else None
