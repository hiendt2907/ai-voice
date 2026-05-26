import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: 'oklch(97% 0.02 250)',
          500: 'oklch(55% 0.2 250)',
          600: 'oklch(47% 0.22 250)',
          900: 'oklch(20% 0.12 250)',
        },
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

export default config
