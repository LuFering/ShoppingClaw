import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    build: {
      /**
       * 把体积大且相互独立的可视化库拆成单独 chunk。
       * 不只是为了缓存：整包一起压缩时 rollup 的峰值内存很高，
       * 而服务器只有 2G 内存 —— 引入 @antv/g6 后曾把构建直接打到 OOM。
       * 拆开之后每个 chunk 单独压缩，峰值明显下降。
       */
      chunkSizeWarningLimit: 1600,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined
            if (id.includes('@antv')) return 'vendor-g6'
            if (/[\\/]d3(-[a-z]+)?[\\/]/.test(id)) return 'vendor-d3'
            if (id.includes('echarts') || id.includes('zrender')) return 'vendor-echarts'
            return undefined
          }
        }
      }
    },
    server: {
      proxy: {
        '^/api': {
          target: env.VITE_API_URL || 'http://localhost:5050',
          changeOrigin: true
        }
      },
      watch: {
        usePolling: true,
        ignored: ['**/node_modules/**', '**/dist/**'],
      },
      host: '0.0.0.0',
    }
  }
})
