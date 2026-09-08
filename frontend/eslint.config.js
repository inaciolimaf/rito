import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

import noDangerousHtml from "./eslint-rules/no-dangerous-html.js";
import noLiteralTailwindColor from "./eslint-rules/no-literal-tailwind-color.js";
import noLoadingWithoutError from "./eslint-rules/no-loading-without-error.js";

export default tseslint.config(
  { ignores: ["dist", ".vite", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { window: "readonly", document: "readonly" },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      rito: {
        rules: {
          "no-dangerous-html": noDangerousHtml,
          "no-literal-tailwind-color": noLiteralTailwindColor,
          "no-loading-without-error": noLoadingWithoutError,
        },
      },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "rito/no-dangerous-html": "error",
      "rito/no-literal-tailwind-color": "error",
      "rito/no-loading-without-error": "error",
    },
  },
);
