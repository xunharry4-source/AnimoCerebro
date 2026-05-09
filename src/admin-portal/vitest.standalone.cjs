const react = require('@vitejs/plugin-react');

module.exports = {
  plugins: [react.default ? react.default() : react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  }
};
