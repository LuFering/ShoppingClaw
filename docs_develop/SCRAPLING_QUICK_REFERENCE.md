# Scrapling MCP 快速参考

## 📦 安装（一次性）

```bash
# 1. 安装依赖（需关闭所有Python进程）
uv add "scrapling[ai]" --link-mode=copy

# 2. 安装浏览器
scrapling install
```

## 🔧 工具概览

### `web_scrape` - 单页抓取

**参数**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| url | str | - | 目标URL |
| method | str | "fetch" | get/fetch/stealthy_fetch |
| css_selector | str | None | CSS选择器（可选） |
| extraction_type | str | "markdown" | markdown/html/text |
| wait_for_network_idle | bool | True | 等待网络空闲 |
| timeout | int | 30 | 超时秒数 |
| main_content_only | bool | True | 只提取主要内容 |

**返回值**: str（提取的内容）

---

### `bulk_web_scrape` - 批量抓取

**参数**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| urls | List[str] | - | URL列表 |
| method | str | "fetch" | get/fetch/stealthy_fetch |
| css_selector | str | None | CSS选择器（应用于所有URL） |
| extraction_type | str | "markdown" | markdown/html/text |
| wait_for_network_idle | bool | True | 等待网络空闲 |
| timeout | int | 30 | 单个URL超时秒数 |
| max_concurrent | int | 3 | 最大并发数 |

**返回值**: Dict[str, str] {url: content}

---

## 💡 使用示例

### 快速抓取静态页面
```python
content = await web_scrape.arun(
    url="https://example.com",
    method="get"
)
```

### 精准提取特定元素
```python
price = await web_scrape.arun(
    url="https://shop.com/product",
    method="fetch",
    css_selector=".product-price",
    extraction_type="text"
)
```

### 绕过Cloudflare保护
```python
content = await web_scrape.arun(
    url="https://protected-site.com",
    method="stealthy_fetch",
    wait_for_network_idle=True,
    timeout=60
)
```

### 批量抓取多个页面
```python
results = await bulk_web_scrape.arun(
    urls=[
        "https://shop.com/product-a",
        "https://shop.com/product-b",
        "https://shop.com/product-c"
    ],
    method="get",
    max_concurrent=2
)
```

---

## 🎯 Method选择指南

| 场景 | 推荐Method | 速度 | 成功率 |
|------|-----------|------|--------|
| 静态HTML页面 | `get` | ⚡⚡⚡ 最快 | ✅ 高 |
| JavaScript动态渲染 | `fetch` | ⚡⚡ 中等 | ✅✅ 很高 |
| Cloudflare/反爬虫 | `stealthy_fetch` | ⚡ 较慢 | ✅✅✅ 极高 |

**经验法则**: 
- 先用`get`尝试，失败再升级到`fetch`
- 明确知道有保护时用`stealthy_fetch`

---

## ⚠️ 常见错误

### 1. ImportError: cannot import name 'dumps' from 'orjson'
**原因**: orjson文件被Python进程锁定  
**解决**: 关闭所有Python进程后重新安装
```bash
uv add "scrapling[ai]" --link-mode=copy
```

### 2. 抓取返回空内容
**可能原因**: 
- CSS选择器不匹配
- 网站需要JavaScript渲染但用了`method="get"`
- 触发了反爬虫机制

**解决**:
```python
# 检查CSS选择器是否正确
# 切换到浏览器模式
method="fetch"
# 或启用反爬虫模式
method="stealthy_fetch"
```

### 3. 超时错误
**解决**: 增加timeout或优化选择器
```python
timeout=60  # 增加到60秒
wait_for_network_idle=True  # 确保页面完全加载
```

---

## 🔍 CSS选择器速查

```css
/* 类选择器 */
.product-price          /* class="product-price" */

/* ID选择器 */
#main-content           /* id="main-content" */

/* 标签选择器 */
h1                      /* 所有<h1>标签 */

/* 属性选择器 */
a[href*="/product/"]    /* href包含"/product/"的链接 */
[data-qa="price"]       /* data-qa="price"的元素 */

/* 组合选择器 */
div.product > h2.title  /* .product下的直接子元素h2.title */
```

**提示**: 让LLM帮你写CSS选择器！
```
"帮我写一个CSS选择器来提取产品页面的价格元素"
```

---

## 📊 性能优化技巧

### 1. 减少Token消耗
```python
# ✅ 好：只提取需要的内容
css_selector=".review-text"
main_content_only=True

# ❌ 差：返回整个页面
css_selector=None
main_content_only=False
```

### 2. 控制并发避免被封
```python
# 批量抓取时限制并发数
max_concurrent=2  # 保守值
max_concurrent=5  # 激进值（风险较高）
```

### 3. 合理设置超时
```python
# 简单页面
timeout=10

# 复杂动态页面
timeout=30

# 有反爬虫保护的页面
timeout=60
```

---

## 🛡️ 法律合规提醒

使用前请确认：
- [ ] 已阅读目标网站的robots.txt
- [ ] 遵守服务条款
- [ ] 尊重版权和知识产权
- [ ] 控制请求频率，不过度负载服务器
- [ ] 不抓取个人隐私数据

---

## 📖 更多资源

- [完整集成报告](../docs_develop/scrapling_integration_report.md)
- [Scrapling官方文档](../docs_develop/srapling_mcp.md)
- [使用示例脚本](../../test/examples/scrapling_usage_examples.py)
- [测试脚本](../../test/test_scrapling_integration.py)

---

**最后更新**: 2026-04-28
