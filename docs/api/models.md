# 模型配置 API（/api/models/*）

管理 LLM 模型配置（多供应商：SiliconFlow/Ollama 等），全部需要
`Authorization: Bearer`，管理员角色可写。

## 端点一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/models/` | 配置列表 → `List[dict]` |
| POST | `/api/models/` | 新增配置 |
| PUT | `/api/models/{config_id}` | 更新配置 |
| DELETE | `/api/models/{config_id}` | 删除配置 |
| POST | `/api/models/{config_id}/set-default` | 设为默认 |
| GET | `/api/models/default` | 当前默认配置 |

## 配置对象字段（以 GET 返回为准）

```json
{
  "provider": "siliconflow | ollama | ...",
  "model_name": "Qwen/Qwen2.5-7B-Instruct",
  "api_base": "https://api.siliconflow.cn/v1",
  "api_key": "sk-***（回显脱敏）",
  "is_default": false,
  "created_at": "..."
}
```

## 语义说明

- 供应商经统一 client 适配（OpenAI 兼容为主 + Ollama）。
- `set-default` 与对话 body `config.model` 联动：对话请求可指定模型名，
  未指定用默认。
- 删除默认配置前先转移默认，避免对话回退异常。
- 环境变量中的 `SILICONFLOW_API_KEY` 是系统兜底凭据；此 API 管理的配置
  是数据库级覆盖。
