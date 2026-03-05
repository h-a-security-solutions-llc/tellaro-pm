import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'
import vueTsEslintConfig from '@vue/eslint-config-typescript'

export default tseslint.config(
  {
    files: ['**/*.{ts,mts,tsx,vue}'],
  },
  ...pluginVue.configs['flat/essential'],
  ...vueTsEslintConfig(),
  {
    rules: {
      'no-console': 'warn',
      'no-debugger': 'warn',
    },
  },
  {
    ignores: ['dist/**', 'coverage/**', 'playwright-report/**'],
  },
)
