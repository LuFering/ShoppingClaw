export function handleChatError(error, context = '') {
  console.error(`[ChatError:${context}]`, error)
}

export function handleValidationError(error) {
  console.error('[ValidationError]', error)
}
