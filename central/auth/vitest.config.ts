import { configDefaults, defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    exclude: [...configDefaults.exclude, 'dist/**'],
    maxWorkers: 1,
    fileParallelism: false,
    disableConsoleIntercept: false,
  },
});
