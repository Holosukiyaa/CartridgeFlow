import '@testing-library/jest-dom/vitest'

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(globalThis, 'ResizeObserver', { configurable: true, writable: true, value: TestResizeObserver })
Object.defineProperty(window, 'ResizeObserver', { configurable: true, writable: true, value: TestResizeObserver })
