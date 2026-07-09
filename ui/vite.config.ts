import { defineConfig } from 'vite';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Base Vite config (alias + shared options).
 * Production page builds go through scripts/build-vite.mjs (one IIFE per entry).
 */
export default defineConfig({
  root: __dirname,
  publicDir: false,
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
});
