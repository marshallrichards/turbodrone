import type { Config } from 'tailwindcss';

export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        heading: ['Rajdhani', 'ui-sans-serif', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
