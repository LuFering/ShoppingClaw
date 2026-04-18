import asyncio
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

async def test_aliyun_model():
    """测试阿里云 DashScope 模型连通性"""
    
    # 1. 获取配置
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_name = "tongyi-xiaomi-analysis-flash"  # 建议使用通用模型测试，tongyi-xiaomi-analysis-flash 可能需要特定权限
    
    print(f"正在测试模型: {model_name}")
    print(f"API Key 前缀: {api_key[:10] if api_key else '未找到'}...")
    
    if not api_key or api_key == "DASHSCOPE_API_KEY":
        print("❌ 错误: 未在 .env 文件中找到有效的 DASHSCOPE_API_KEY")
        return

    try:
        from langchain_openai import ChatOpenAI
        
        # 2. 初始化模型
        llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7
        )
        
        # 3. 发送测试消息
        print("🚀 正在发送测试请求...")
        response = await llm.ainvoke("你使用的是什么模型")
        
        print("\n✅ 连通性测试成功！")
        print(f"模型回复: {response.content}")
        
    except Exception as e:
        print(f"\n❌ 连通性测试失败: {str(e)}")
        if "401" in str(e):
            print("提示: 401 错误通常意味着 API Key 无效或已过期，请检查阿里云控制台。")
        elif "404" in str(e):
            print(f"提示: 404 错误可能意味着模型名称 '{model_name}' 不正确或不可用。")

if __name__ == "__main__":
    asyncio.run(test_aliyun_model())
