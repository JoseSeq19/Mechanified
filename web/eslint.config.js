/**
 * Configuración de ESLint para la web.
 *
 * Formato plano (`eslint.config.js`), que es el único que acepta ESLint 10.
 * Por eso el script de `package.json` ya no lleva `--ext`: esa opción
 * desapareció con el formato viejo, y era lo que hacía fallar `npm run lint`.
 *
 * No se apoya en `@eslint/js` ni en `globals`, que no están instalados: las
 * reglas base de ESLint vienen apagadas por omisión y TypeScript ya avisa de
 * las variables que no existen, así que no hacen falta.
 *
 * Sin reglas con información de tipos (`recommended-type-checked`): obligan a
 * compilar el proyecto entero en cada pasada, y aquí `npm run typecheck` ya
 * hace ese trabajo. Lo que se busca en el linter es lo que el compilador no
 * mira.
 */
import tseslint from '@typescript-eslint/eslint-plugin';
import parser from '@typescript-eslint/parser';

export default [
  { ignores: ['dist/**', 'node_modules/**'] },

  ...tseslint.configs['flat/recommended'],

  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser,
      ecmaVersion: 2023,
      sourceType: 'module',
    },
    rules: {
      // El guion bajo es la marca de "esto sobra y lo sé": parámetros que
      // la firma exige y el cuerpo no usa.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],
      // Un `console.log` olvidado acaba en producción sin que nadie lo note.
      // Avisar de error y advertencia sí es legítimo.
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },
];
