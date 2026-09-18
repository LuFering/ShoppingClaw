export function mergeChunks(chunks) {
  if (!chunks || !chunks.length) return ''
  return chunks.join('')
}

export function getChunkPreview(chunk) {
  if (!chunk) return ''
  return typeof chunk === 'string' ? chunk.slice(0, 100) : ''
}
