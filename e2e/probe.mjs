// 通用页面探针：node probe.mjs <path>
import { chromium } from 'file:///C:/Users/25153/.workbuddy-ai/binaries/node/workspace/node_modules/playwright-core/index.mjs'

const BASE = 'http://111.229.209.47'
const path = process.argv[2] || '/'

const browser = await chromium.connectOverCDP('http://127.0.0.1:9222')
const ctx = browser.contexts()[0] || (await browser.newContext())
const page = await ctx.newPage()

await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForTimeout(2500)

console.log('URL   :', page.url())
console.log('TITLE :', await page.title())

const info = await page.evaluate(() => {
  const vis = (el) => {
    const r = el.getBoundingClientRect()
    return r.width > 0 && r.height > 0
  }
  return {
    inputs: [...document.querySelectorAll('input,textarea')]
      .filter(vis)
      .map((el) => ({ tag: el.tagName.toLowerCase(), type: el.type || '', id: el.id || '', ph: el.placeholder || '', cls: (el.className || '').toString().slice(0, 50) })),
    buttons: [...document.querySelectorAll('button,.ant-btn')]
      .filter(vis)
      .map((el) => ({ text: (el.innerText || '').trim().slice(0, 24), cls: (el.className || '').toString().slice(0, 60) })),
    bodyText: document.body.innerText.slice(0, 500),
  }
})
console.log('\n=== 输入框 ===\n' + JSON.stringify(info.inputs, null, 2))
console.log('\n=== 按钮 ===\n' + JSON.stringify(info.buttons, null, 2))
console.log('\n=== 文本 ===\n' + info.bodyText)

await page.screenshot({ path: `C:/Users/25153/workbuddy-ai/虾购/e2e/shot${path.replace(/\//g, '_')}.png`, fullPage: true })
await page.close()
await browser.close()
