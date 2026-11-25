import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

import noLiteralTailwindColor from "./eslint-rules/no-literal-tailwind-color.js";

/*
 * Regras do frontend-standard (docs/frontend-standard-audit-guarantees.md).
 *
 * As regras valem para TODO código novo. Arquivo que já violava quando a regra entrou
 * está nas listas DEBT_* abaixo, com a regra desligada para ele — e só para ele. Ao
 * corrigir um desses arquivos, tire-o da lista: a dívida só desce.
 */
const TEST_FILES = ["**/*.test.{ts,tsx}", "src/test/**", "src/mocks/**"];

// max-lines-per-function (100 linhas, sem brancos e comentários): dívida por arquivo.
const DEBT_FUNCTION_SIZE = [
  "src/components/domain/CrudListPage.tsx",
  "src/components/domain/DataTable.tsx",
  "src/components/domain/EntityPicker.tsx",
  "src/components/domain/ImageUploader.tsx",
  "src/components/shell/GlobalSearch.tsx",
  "src/features/action-groups/ActionGroupsListPage.tsx",
  "src/features/ai/AiBudgetPanel.tsx",
  "src/features/ai/CopilotPanel.tsx",
  "src/features/automations/AutomationsSettingsPage.tsx",
  "src/features/automations/LlmDecisionAction.tsx",
  "src/features/comments/CommentEditor.tsx",
  "src/features/crm/CrmPage.tsx",
  "src/features/customers/CustomerForm.tsx",
  "src/features/customers/CustomerListPage.tsx",
  "src/features/documents/DocumentBrowser.tsx",
  "src/features/financial/BankAccountsListPage.tsx",
  "src/features/financial/DunningRulesForm.tsx",
  "src/features/financial/FinancialDashboard.tsx",
  "src/features/financial/FinancialReportPage.tsx",
  "src/features/financial/OverduePanel.tsx",
  "src/features/financial/TransactionForm.tsx",
  "src/features/financial/TransactionsListPage.tsx",
  "src/features/kitchen-sink/KitchenSinkPage.tsx",
  "src/features/lawsuits/LawsuitDetailPage.tsx",
  "src/features/lawsuits/LawsuitForm.tsx",
  "src/features/lawsuits/LawsuitsPage.tsx",
  "src/features/legal-agents/GenerateBriefDialog.tsx",
  "src/features/monitored-terms/MonitoredTermsListPage.tsx",
  "src/features/partners/PartnersPage.tsx",
  "src/features/partners/ShareLawsuitDialog.tsx",
  "src/features/posts/PostListPage.tsx",
  "src/features/posts/TaskForm.tsx",
  "src/features/publications/PublicationDetailDrawer.tsx",
  "src/features/publications/PublicationListPage.tsx",
  "src/features/reports/PipelinePanel.tsx",
  "src/features/reports/ReportPage.tsx",
  "src/features/reports/TimeFeesPanel.tsx",
  "src/features/schedule/CalendarPage.tsx",
  "src/features/stages/StagesListPage.tsx",
  "src/features/task-types/TaskTypesListPage.tsx",
  "src/features/taskscore/GoalsSettingsForm.tsx",
  "src/features/templates/EditorAiAssistant.tsx",
  "src/features/templates/GenerateDocumentDialog.tsx",
  "src/features/templates/TemplateEditor.tsx",
  "src/features/templates/TemplateEditorPage.tsx",
  "src/features/templates/TemplatesListPage.tsx",
  "src/features/users/UserForm.tsx",
  "src/features/users/UsersListPage.tsx",
  "src/features/webhooks/WebhooksSettingsPage.tsx",
  "src/features/workflows/WorkflowEditor.tsx",
  "src/features/workflows/WorkflowPreviewDialog.tsx",
  "src/features/workflows/WorkflowsListPage.tsx",
];

// max-lines (300 linhas por arquivo): dívida por arquivo.
const DEBT_FILE_SIZE = [
  "src/features/customers/CustomerListPage.tsx",
  "src/features/documents/DocumentBrowser.tsx",
  "src/features/financial/TransactionsListPage.tsx",
  "src/features/financial/api.ts",
  "src/features/lawsuits/LawsuitsPage.tsx",
  "src/features/lawsuits/api.ts",
  "src/features/reports/api.ts",
  "src/features/reports/reportDefinitions.tsx",
];

// toLocaleString / toLocaleDateString fora de src/lib: números e datas saem de um lugar só.
const DEBT_FORMATTING = [
  "src/features/action-groups/ActionGroupsListPage.tsx",
  "src/features/ai/AiAuditTrail.tsx",
  "src/features/api-tokens/ApiTokensPage.tsx",
  "src/features/automations/AutomationTestDialog.tsx",
  "src/features/automations/DecisionLogCard.tsx",
  "src/features/automations/RunsTimeline.tsx",
  "src/features/comments/CommentThread.tsx",
  "src/features/customer-origins/CustomerOriginsListPage.tsx",
  "src/features/customers/CustomerListPage.tsx",
  "src/features/documents/DocumentBrowser.tsx",
  "src/features/financial/DunningHistoryDrawer.tsx",
  "src/features/integrations/StalenessIndicator.tsx",
  "src/features/lawsuit-types/LawsuitTypesListPage.tsx",
  "src/features/lawsuits/FolderGroupView.tsx",
  "src/features/lawsuits/LawsuitsPage.tsx",
  "src/features/monitored-terms/MonitoredTermsListPage.tsx",
  "src/features/monitored-terms/SyncRunsTable.tsx",
  "src/features/notifications/NotificationPanel.tsx",
  "src/features/publications/DeadlineReviewField.tsx",
  "src/features/publications/PublicationAnalysisCard.tsx",
  "src/features/publications/PublicationDetailDrawer.tsx",
  "src/features/publications/PublicationListPage.tsx",
  "src/features/reports/LostTimeCard.tsx",
  "src/features/reports/TimeFeesPanel.tsx",
  "src/features/reports/TimesheetCell.tsx",
  "src/features/schedule/calendar.ts",
  "src/features/squads/SquadsListPage.tsx",
  "src/features/stages/StagesListPage.tsx",
  "src/features/task-types/TaskTypesListPage.tsx",
  "src/features/templates/TemplatesListPage.tsx",
  "src/features/users/UsersListPage.tsx",
  "src/features/webhooks/DeliveryLog.tsx",
  "src/features/workflows/WorkflowPreviewDialog.tsx",
];

// addEventListener("keydown") fora de um hook: teclado escutado em um lugar só.
const DEBT_KEYBOARD = [
  "src/components/domain/useClickOutside.ts",
  "src/components/shell/GlobalSearch.tsx",
  "src/features/ai/CopilotPanel.tsx",
  "src/features/templates/AiSuggestionOverlay.tsx",
  "src/features/templates/EditorAiAssistant.tsx",
  "src/features/templates/SlashCommandMenu.tsx",
];

// `@/features/*` importado de components/domain, components/ui ou lib (camada de baixo).
const DEBT_LAYER = ["src/components/domain/IntegrationAlertBanner.tsx"];

const RESTRICTED_LOCALE_METHODS = [
  "toLocaleString",
  "toLocaleDateString",
  "toLocaleTimeString",
].map((property) => ({
  property,
  message:
    "Formate números e datas por src/lib (money.ts, utils.ts) em vez de chamar toLocale* direto (frontend-standard).",
}));

export default tseslint.config(
  // generated/api-schema.ts é gerado do openapi.json (make api-types): não se lint nem se edita.
  { ignores: ["dist", ".vite", "node_modules", "generated/api-schema.ts"] },
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
      rito: { rules: { "no-literal-tailwind-color": noLiteralTailwindColor } },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-hooks/exhaustive-deps": "error", // hook sem dependência declarada: erro, não aviso
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "rito/no-literal-tailwind-color": "error",
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: [...TEST_FILES, ...DEBT_FILE_SIZE],
    rules: {
      "max-lines": ["error", { max: 300, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: [...DEBT_FUNCTION_SIZE, ...TEST_FILES],
    rules: {
      "max-lines-per-function": [
        "error",
        { max: 100, skipBlankLines: true, skipComments: true, IIFEs: true },
      ],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/lib/**", ...DEBT_FORMATTING],
    rules: {
      "no-restricted-properties": ["error", ...RESTRICTED_LOCALE_METHODS],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: DEBT_KEYBOARD,
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "CallExpression[callee.property.name='addEventListener'][arguments.0.value='keydown']",
          message: "Escute o teclado em um hook só (frontend-standard), não no componente.",
        },
        {
          selector: "CallExpression[callee.name='useParams'][arguments.length>0]",
          message:
            "Leia os parâmetros da rota com useParams() sem argumentos e valide no componente da rota (frontend-standard).",
        },
      ],
    },
  },
  {
    files: ["src/components/domain/**", "src/components/ui/**", "src/lib/**"],
    ignores: DEBT_LAYER,
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/features/*"],
              message:
                "Componente genérico e lib não importam feature (frontend-standard, camadas).",
            },
          ],
        },
      ],
    },
  },
);
