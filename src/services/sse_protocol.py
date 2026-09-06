"""
SSE 事件协议定义 - 参考 ScienceClaw 的结构化事件系统

EventType 枚举定义了所有支持的 SSE 事件类型，用于前端 Agent 流程可视化。
"""
from enum import Enum


class EventType(str, Enum):
    """
    SSE 事件类型枚举
    
    分类:
    - 消息类: message_chunk, message_chunk_done, message
    - 思考类: thinking
    - 计划类: plan, plan_update
    - 步骤类: step_start, step_complete
    - 工具类: tool_start, tool_complete
    - 统计类: statistics
    - 控制类: init, done, error, title
    """
    
    # ═══ 消息类 (Message Events) ═══
    MESSAGE_CHUNK = "message_chunk"       # 流式文本块（增量）
    MESSAGE_CHUNK_DONE = "message_chunk_done"  # 流式文本块结束
    MESSAGE = "message"                   # 完整消息
    
    # ═══ 思考类 (Thinking Events) ═══
    THINKING = "thinking"                 # 推理/思考内容
    
    # ═══ 计划类 (Plan Events) ═══
    PLAN = "plan"                         # 初始计划
    PLAN_UPDATE = "plan_update"           # 计划更新
    
    # ═══ 步骤类 (Step Events) ═══
    STEP_START = "step_start"             # 步骤开始
    STEP_COMPLETE = "step_complete"       # 步骤完成
    
    # ═══ 工具类 (Tool Events) ═══
    TOOL_START = "tool_start"             # 工具调用开始
    TOOL_COMPLETE = "tool_complete"       # 工具调用完成
    
    # ═══ 统计类 (Statistics Events) ═══
    STATISTICS = "statistics"             # Token/耗时统计
    
    # ═══ 控制类 (Control Events) ═══
    INIT = "init"                         # 初始化
    DONE = "done"                         # 完成
    ERROR = "error"                       # 错误
    TITLE = "title"                       # 自动标题
