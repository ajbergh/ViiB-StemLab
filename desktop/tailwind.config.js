/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          0: '#0B0B0E', // Main background
          1: '#121216', // Cards / Panels
          2: '#18181E', // Raised surfaces / Hover states
          3: '#24242B', // Borders / Dividers
        },
        text: {
          main: 'rgba(255,255,255,0.92)',
          secondary: '#B8BAC6',
          subtle: '#7A7D8C',
        },
        brand: {
          DEFAULT: '#9B5CFF',
          hover: '#A970FF',
          dark: '#7A3EE0',
        },
        accent: {
          purple: '#9B5CFF',
          green: '#3EE089',
          orange: '#FF9F43',
          blue: '#4EA1FF',
          crimson: '#FF5D5D',
        },
        status: {
          success: '#3EE089',
          warning: '#FF9F43',
          error: '#FF5D5D',
          info: '#4EA1FF',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      borderRadius: {
        xl: '12px',
      },
    },
  },
  plugins: [],
}
