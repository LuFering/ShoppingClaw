"""
Scrapling MCP 工具使用示例

展示如何在researcher子智能体中使用web_scrape和bulk_web_scrape工具
"""
import asyncio


# ============================================================
# 示例1: 基本网页抓取
# ============================================================
async def example_basic_scrape():
    """示例1: 抓取单个静态页面"""
    from src.agents.common.toolkits.research.scrapling_tools import web_scrape
    
    print("=" * 80)
    print("示例1: 基本网页抓取")
    print("=" * 80)
    
    # 抓取example.com
    result = await web_scrape.arun(
        url="https://example.com",
        method="get",  # 静态页面用get最快
        extraction_type="markdown"
    )
    
    print(f"\n结果预览:\n{result[:500]}...\n")
    return result


# ============================================================
# 示例2: 使用CSS选择器精准提取
# ============================================================
async def example_css_selector():
    """示例2: 使用CSS选择器提取特定元素"""
    from src.agents.common.toolkits.research.scrapling_tools import web_scrape
    
    print("=" * 80)
    print("示例2: CSS选择器精准提取")
    print("=" * 80)
    
    # 假设我们要提取某个电商网站的价格
    # 这里用wikipedia作为示例
    result = await web_scrape.arun(
        url="https://en.wikipedia.org/wiki/Web_scraping",
        method="get",
        css_selector=".mw-page-title-main",  # 提取主标题
        extraction_type="text"
    )
    
    print(f"\n提取的标题: {result}\n")
    return result


# ============================================================
# 示例3: 动态内容抓取
# ============================================================
async def example_dynamic_content():
    """示例3: 抓取需要JavaScript渲染的动态页面"""
    from src.agents.common.toolkits.research.scrapling_tools import web_scrape
    
    print("=" * 80)
    print("示例3: 动态内容抓取")
    print("=" * 80)
    
    # 对于需要JS渲染的页面，使用fetch模式
    result = await web_scrape.arun(
        url="https://example.com",
        method="fetch",  # 浏览器模式
        wait_for_network_idle=True,  # 等待网络空闲
        timeout=30
    )
    
    print(f"\n结果长度: {len(result)} 字符\n")
    return result


# ============================================================
# 示例4: 批量并发抓取
# ============================================================
async def example_bulk_scrape():
    """示例4: 批量抓取多个页面"""
    from src.agents.common.toolkits.research.scrapling_tools import bulk_web_scrape
    
    print("=" * 80)
    print("示例4: 批量并发抓取")
    print("=" * 80)
    
    urls = [
        "https://example.com",
        "https://example.org",
        "https://example.net"
    ]
    
    results = await bulk_web_scrape.arun(
        urls=urls,
        method="get",
        max_concurrent=2,  # 最多同时抓取2个
        extraction_type="markdown"
    )
    
    for url, content in results.items():
        if not url.startswith("error"):
            print(f"\n{url}: {len(content)} 字符")
    
    return results


# ============================================================
# 示例5: 实际电商场景模拟
# ============================================================
async def example_ecommerce_scenario():
    """示例5: 模拟电商研究场景"""
    from src.agents.common.toolkits.research.scrapling_tools import web_scrape
    
    print("=" * 80)
    print("示例5: 电商场景 - 获取产品评测")
    print("=" * 80)
    
    # 场景: Researcher需要从评测网站收集iPhone 15 Pro的用户反馈
    # 这里用示例URL演示
    review_url = "https://example.com/reviews/iphone-15-pro"
    
    result = await web_scrape.arun(
        url=review_url,
        method="fetch",
        css_selector=".review-text",  # 只提取评测正文
        extraction_type="markdown",
        main_content_only=True  # 过滤广告和导航
    )
    
    print(f"\n收集的评测内容:\n{result[:300]}...\n")
    return result


# ============================================================
# 示例6: 错误处理演示
# ============================================================
async def example_error_handling():
    """示例6: 错误处理"""
    from src.agents.common.toolkits.research.scrapling_tools import web_scrape
    
    print("=" * 80)
    print("示例6: 错误处理")
    print("=" * 80)
    
    # 测试无效URL
    result = await web_scrape.arun(
        url="https://this-domain-does-not-exist-12345.com",
        method="get",
        timeout=5
    )
    
    print(f"\n错误响应: {result}\n")
    
    # 测试无效的CSS选择器
    result = await web_scrape.arun(
        url="https://example.com",
        method="get",
        css_selector=".non-existent-class-xyz",
        extraction_type="text"
    )
    
    print(f"无效选择器响应: {result}\n")
    
    return result


# ============================================================
# 主函数 - 运行所有示例
# ============================================================
async def main():
    """运行所有示例"""
    print("\n🚀 Scrapling MCP 工具使用示例\n")
    
    examples = [
        ("基本网页抓取", example_basic_scrape),
        ("CSS选择器提取", example_css_selector),
        ("动态内容抓取", example_dynamic_content),
        ("批量并发抓取", example_bulk_scrape),
        ("电商场景模拟", example_ecommerce_scenario),
        ("错误处理", example_error_handling),
    ]
    
    for name, func in examples:
        try:
            print(f"\n{'='*80}")
            print(f"运行示例: {name}")
            print(f"{'='*80}\n")
            
            await func()
            
            # 添加分隔
            input("\n按回车继续下一个示例...")
            print()
            
        except Exception as e:
            print(f"\n❌ 示例失败: {type(e).__name__}: {e}\n")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ 所有示例执行完成！")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    # 注意: 需要先修复orjson依赖才能正常运行
    print("⚠️  提示: 确保已执行以下命令:")
    print("   1. uv add scrapling[ai] --link-mode=copy")
    print("   2. scrapling install")
    print()
    
    choice = input("是否继续运行示例？(y/n): ").strip().lower()
    if choice == 'y':
        asyncio.run(main())
    else:
        print("已取消")
