import fs from 'node:fs';
import { defineConfig } from 'tsup';

const pkg = JSON.parse(fs.readFileSync(new URL('./package.json', import.meta.url), 'utf8'));
const external = Object.keys(pkg.dependencies ?? {});
const sourcemap = process.env.UNICRON_APPLIANCE_BUILD === 'true' ? false : true;

export default defineConfig({
  entry: ['src/index.ts'],
  format: ['esm'],
  target: 'node20',
  platform: 'node',
  outDir: 'dist',
  sourcemap,
  clean: true,
  splitting: false,
  bundle: true,
  external,
});
