import test from 'node:test'
import assert from 'node:assert/strict'
import { request } from '../src/api.ts'

test('successful API responses preserve workflow tokens', async (context) => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  const storage = new Map<string, string>()
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      location: { search: '', href: 'http://127.0.0.1/capabilities/', pathname: '/capabilities/', hash: '' },
      history: { replaceState() {} },
      sessionStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => storage.set(key, value),
      },
    },
  })
  globalThis.fetch = async () => new Response(JSON.stringify({
    verification: { token: 'verify_1234567890abcdef' },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  context.after(() => {
    globalThis.fetch = originalFetch
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow })
  })

  const result = await request<{ verification: { token: string } }>('/proof')
  assert.equal(result.verification.token, 'verify_1234567890abcdef')
})
