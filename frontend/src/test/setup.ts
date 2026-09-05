import '@testing-library/jest-dom'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

beforeEach(() => {
  window.localStorage.removeItem('legado.locale')
  Object.defineProperty(window, 'scrollTo', { configurable: true, writable: true, value: vi.fn() })
})

afterEach(() => {
  cleanup()
})
