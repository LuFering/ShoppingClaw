"""历史消息管理器 - 三重截断保护机制

参考 ScienceClaw 的设计，实现三层防护避免上下文溢出：
1. 单条消息截断：限制单条消息的最大长度
2. 轮数截断：保留最近 N 轮对话
3. Token 预算截断：基于 token 预算裁剪历史

核心目标：在有限的 context window 内，保留最有价值的历史信息。
"""
import logging
from typing import List

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)


class HistoryManager:
    """三重保护的历史消息管理
    
    设计原则：
    1. 保守估计：预留足够的安全边界
    2. 优先级：System > 最近对话 > 工具结果
    3. 可配置：所有阈值可通过参数调整
    """
    
    # 默认阈值
    MAX_ASSISTANT_CHARS = 3000      # 单条助手消息最大字符数
    MAX_TOOL_RESULT_CHARS = 2000    # 单条工具结果最大字符数
    MAX_TOOL_ARGS_CHARS = 500       # 单条工具参数最大字符数
    MAX_ROUNDS = 10                 # 最大对话轮数
    SAFETY_MARGIN_TOKENS = 4096     # 安全边界（token）
    
    def __init__(
        self,
        max_assistant_chars: int = None,
        max_tool_result_chars: int = None,
        max_rounds: int = None,
        safety_margin_tokens: int = None,
    ):
        """初始化 HistoryManager
        
        Args:
            max_assistant_chars: 单条助手消息最大字符数
            max_tool_result_chars: 单条工具结果最大字符数
            max_rounds: 最大对话轮数
            safety_margin_tokens: 安全边界 token 数
        """
        self.MAX_ASSISTANT_CHARS = max_assistant_chars or self.MAX_ASSISTANT_CHARS
        self.MAX_TOOL_RESULT_CHARS = max_tool_result_chars or self.MAX_TOOL_RESULT_CHARS
        self.MAX_ROUNDS = max_rounds or self.MAX_ROUNDS
        self.SAFETY_MARGIN_TOKENS = safety_margin_tokens or self.SAFETY_MARGIN_TOKENS
    
    def build_history_messages(
        self,
        session_events: list[dict],
        context_window: int = 64000,
        max_tokens: int = 8192,
        output_reserve: int = 16384,
    ) -> list[BaseMessage]:
        """从会话事件重建历史消息，带三层截断保护
        
        Args:
            session_events: 会话事件列表（从数据库加载的 messages 字段）
            context_window: 模型的 context window 大小
            max_tokens: 最大生成 token 数
            output_reserve: 为输出预留的 token 数
            
        Returns:
            截断后的消息列表
        """
        if not session_events:
            return []
        
        messages = []
        
        # Step 1: 重建消息对象
        for event in session_events:
            msg = self._reconstruct_message(event)
            if msg is None:
                continue
            
            # Step 2: 单条消息截断
            msg = self._truncate_single_message(msg)
            
            messages.append(msg)
        
        if not messages:
            return []
        
        # Step 3: 基于轮数的裁剪
        messages = self._trim_by_rounds(messages, self.MAX_ROUNDS)
        
        # Step 4: 基于 Token 预算的裁剪
        budget = self._compute_token_budget(context_window, max_tokens, output_reserve)
        messages = self._trim_by_token_budget(messages, budget)
        
        logging.info(
            f"[HistoryManager] Built {len(messages)} messages "
            f"(budget={budget} tokens)"
        )
        
        return messages
    
    def _reconstruct_message(self, event: dict) -> BaseMessage | None:
        """从事件字典重建消息对象
        
        Args:
            event: 消息事件字典，格式如：
                {"role": "human", "content": "..."}
                {"role": "ai", "content": "...", "tool_calls": [...]}
                {"role": "tool", "content": "...", "tool_call_id": "..."}
                
        Returns:
            BaseMessage 对象，或 None（如果无法重建）
        """
        role = event.get("role")
        content = event.get("content", "")
        
        if not role or not content:
            return None
        
        try:
            if role == "human":
                return HumanMessage(content=content)
            elif role == "ai":
                additional_kwargs = {}
                if "tool_calls" in event:
                    additional_kwargs["tool_calls"] = event["tool_calls"]
                if "reasoning_content" in event:
                    additional_kwargs["reasoning_content"] = event["reasoning_content"]
                
                return AIMessage(
                    content=content,
                    additional_kwargs=additional_kwargs if additional_kwargs else {},
                )
            elif role == "tool":
                return ToolMessage(
                    content=content,
                    tool_call_id=event.get("tool_call_id", ""),
                )
            elif role == "system":
                return SystemMessage(content=content)
            else:
                logging.warning(f"[HistoryManager] Unknown role: {role}")
                return None
                
        except Exception as e:
            logging.error(f"[HistoryManager] Failed to reconstruct message: {e}")
            return None
    
    def _truncate_single_message(self, msg: BaseMessage) -> BaseMessage:
        """截断单条消息到合理长度
        
        Args:
            msg: 原始消息对象
            
        Returns:
            截断后的消息对象
        """
        if isinstance(msg, AIMessage):
            if len(msg.content) > self.MAX_ASSISTANT_CHARS:
                truncated = msg.content[:self.MAX_ASSISTANT_CHARS] + "\n...[内容过长已截断]"
                msg.content = truncated
                logging.debug(
                    f"[HistoryManager] Truncated AI message to {self.MAX_ASSISTANT_CHARS} chars"
                )
        
        elif isinstance(msg, ToolMessage):
            if len(msg.content) > self.MAX_TOOL_RESULT_CHARS:
                truncated = msg.content[:self.MAX_TOOL_RESULT_CHARS] + "\n...[结果过长已截断]"
                msg.content = truncated
                logging.debug(
                    f"[HistoryManager] Truncated tool result to {self.MAX_TOOL_RESULT_CHARS} chars"
                )
        
        return msg
    
    def _trim_by_rounds(
        self,
        messages: list[BaseMessage],
        max_rounds: int,
    ) -> list[BaseMessage]:
        """保留最近 N 轮对话
        
        一轮对话 = 1个 HumanMessage + 1个或多个 AI/Tool 消息
        
        Args:
            messages: 消息列表
            max_rounds: 最大轮数
            
        Returns:
            截断后的消息列表
        """
        if len(messages) <= max_rounds * 2:  # 快速路径
            return messages
        
        # 从后往前计数 HumanMessage 作为轮次边界
        rounds = 0
        cutoff_index = 0
        
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                rounds += 1
                if rounds >= max_rounds:
                    cutoff_index = i
                    break
        
        if cutoff_index > 0:
            # 保留 System 消息（如果有）
            result = []
            for msg in messages[:cutoff_index]:
                if isinstance(msg, SystemMessage):
                    result.append(msg)
            
            result.extend(messages[cutoff_index:])
            logging.info(
                f"[HistoryManager] Trimmed by rounds: {len(messages)} -> {len(result)} "
                f"(kept {rounds} rounds)"
            )
            return result
        
        return messages
    
    def _trim_by_token_budget(
        self,
        messages: list[BaseMessage],
        budget: int,
    ) -> list[BaseMessage]:
        """按 token 预算裁剪，保留最近的消息

        策略：
        1. 始终保留 System 消息
        2. 从后往前累加 token，直到超出预算
        3. 裁切线对齐到 HumanMessage 边界，保证 tool_calls/tool_message 配对完整
        4. 优先保留最近的对话

        Args:
            messages: 消息列表
            budget: token 预算

        Returns:
            截断后的消息列表
        """
        if not messages:
            return []

        # 分离 System 消息和其他消息
        system_messages = [m for m in messages if isinstance(m, SystemMessage)]
        other_messages = [m for m in messages if not isinstance(m, SystemMessage)]

        if not other_messages:
            return messages

        # 计算 System 消息的 token 占用
        system_tokens = sum(self._estimate_tokens(m) for m in system_messages)
        remaining_budget = budget - system_tokens

        if remaining_budget <= 0:
            logging.warning(
                "[HistoryManager] Budget exhausted by system messages only"
            )
            return system_messages

        # 从后往前累加 token，对齐到 HumanMessage 边界
        total_tokens = 0
        cutoff_index = len(other_messages)

        for i in range(len(other_messages) - 1, -1, -1):
            msg_tokens = self._estimate_tokens(other_messages[i])
            total_tokens += msg_tokens

            if total_tokens > remaining_budget:
                cutoff_index = i + 1
                break

        # 对齐到最近的 HumanMessage 边界，确保 tool_calls/tool_message 不被打断
        while cutoff_index < len(other_messages) and not isinstance(other_messages[cutoff_index], HumanMessage):
            cutoff_index += 1

        result = system_messages + other_messages[cutoff_index:]

        if len(result) < len(messages):
            logging.info(
                f"[HistoryManager] Trimmed by token budget: "
                f"{len(messages)} -> {len(result)} messages "
                f"(budget={budget}, used≈{total_tokens + system_tokens})"
            )

        return result
    
    def _compute_token_budget(
        self,
        context_window: int,
        max_tokens: int = 8192,
        output_reserve: int = 16384,
    ) -> int:
        """计算可用于历史的 token 预算
        
        公式：
        budget = context_window - max_tokens - output_reserve - safety_margin
        
        Args:
            context_window: 模型的 context window 大小
            max_tokens: 最大生成 token 数
            output_reserve: 为输出预留的 token 数
            
        Returns:
            可用于历史的 token 预算
        """
        budget = (
            context_window
            - max_tokens
            - output_reserve
            - self.SAFETY_MARGIN_TOKENS
        )
        
        # 确保预算不为负
        budget = max(budget, 1024)  # 至少保留 1024 token
        
        logging.debug(
            f"[HistoryManager] Token budget: {budget} "
            f"(context={context_window}, max_tokens={max_tokens}, "
            f"output_reserve={output_reserve}, safety={self.SAFETY_MARGIN_TOKENS})"
        )
        
        return budget
    
    def _estimate_tokens(self, msg: BaseMessage) -> int:
        """估算消息的 token 数量
        
        简化估算：每 4 个字符 ≈ 1 个 token
        （更精确的方案可使用 tiktoken 库）
        
        Args:
            msg: 消息对象
            
        Returns:
            估算的 token 数量
        """
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        
        # 基础 token 数
        tokens = len(content) // 4
        
        # 额外开销：角色标记、工具调用等
        if isinstance(msg, AIMessage):
            tokens += 10  # AI 消息的额外开销
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tokens += len(msg.tool_calls) * 20  # 每个工具调用约 20 token
        elif isinstance(msg, ToolMessage):
            tokens += 15  # Tool 消息的额外开销
        elif isinstance(msg, HumanMessage):
            tokens += 5  # Human 消息的额外开销
        
        return max(tokens, 1)  # 至少 1 个 token
