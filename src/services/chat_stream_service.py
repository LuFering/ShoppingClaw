import json

from langchain_core.messages import HumanMessage, AIMessageChunk, AIMessage

from src.agents import agent_manager


def extract_agent_state(values: dict) -> dict:
    todos = values.get("todos")
    result = {
        "todos": list(todos)[:20],
        "files":values.get("files")
    }
    return result
def _ensure_full_msg(full_msg:AIMessage|None,accumulated_content:list[str])->AIMessage|None:
    if not full_msg and accumulated_content:
        return AIMessage(content="".join(accumulated_content))
    return full_msg


async def stream_agent_chat(
        *,
        agent_name: str,
        query: str,
        config: dict,
        meta: dict,
):
    def make_chunk(content=None, **kwargs):
        return (
                json.dump(
                    {"request_id": meta.get("request_id"), "response": content, **kwargs},
                    ensure_ascii=False).encode("utf-8")
                + b"\n"
        )

    human_message = HumanMessage(content=query)
    message_type = "text"
    init_msg = {"role": "user", "content": query, "type": "human"}
    init_msg["message_type"] = message_type
    agent = agent_manager.get_agent(agent_name)
    messages = [human_message]
    agent_config_id = config.get("agent_config_id")
    input_context = {
        "user_id": user_id,
        "thread_id": thread_id,
        "agent_config_id": agent_config_id,
        "agent_config": agent_config,
    }
    langgraph_config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
    full_msg=None
    accumulated_content = []
    async for msg, metadata in agent.stream_messages(messages, input_context=input_context):
        if isinstance(msg, AIMessageChunk):
            accumulated_content.append(msg.content)
            yield make_chunk(content=msg.content, msg=msg.model_dump(), metadata=metadata, status="loading")
        else:
            msg_dict = msg.model_dump()  # 转成dict类型
            yield make_chunk(msg=msg_dict, metadata=metadata, status="loading")
            if msg_dict.get("type") == "tool":
                graph = await agent.get_garph()
                state = await graph.aget_state(langgraph_config)
                agent_state =extract_agent_state(getattr(state,"values",{}))
                yield make_chunk(status="agent_state",agent_state=agent_state,meta=meta)
    full_msg=_ensure_full_msg(full_msg,accumulated_content)
