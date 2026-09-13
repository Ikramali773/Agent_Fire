import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    // Component tests render into a real DOM; the pure helpers don't need
    // one but there aren't enough of either to be worth two environments.
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    // No `globals: true` - describe/it/expect are imported explicitly, so
    // tsconfig.app.json's `types` stays as it is and `tsc -b` type-checks
    // the tests along with the rest of src.
    restoreMocks: true,
  },
})
