 // postcss.config.cjs  (new)
module.exports = {
  plugins: {
    '@tailwindcss/postcss': {},   // ← new v4 plugin
    autoprefixer: {},             // optional but still fine
  },
};