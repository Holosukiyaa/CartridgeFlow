export function visualFrame() {
  if (!import.meta.env.DEV) return ''
  return new URLSearchParams(window.location.search).get('visual') || ''
}
