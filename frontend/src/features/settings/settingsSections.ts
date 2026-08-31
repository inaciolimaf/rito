/** Spec 102, regra 16: o hub de Configurações.
 *
 * `navItems.ts` aponta para `/settings` desde a spec 008, e a rota nunca existiu —
 * clicar em "Configurações" caía no `NotFoundPage`. As 16 telas de configuração
 * existiam todas, cada uma alcançável só por URL direta.
 *
 * Esta lista é a fonte única do hub. Agrupada por assunto, na mesma ordem em que o
 * ADVBOX agrupa: o que é do escritório, o que é cadastro, o que é de processo, de
 * dinheiro, de automação e de IA.
 */
export interface SettingsLink {
  label: string;
  description: string;
  path: string;
  /** Ausente => visível para quem já pode ver o hub. */
  capability?: string;
}

export interface SettingsSection {
  title: string;
  links: SettingsLink[];
}

export const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    title: "Escritório",
    links: [
      {
        label: "Usuários",
        description: "Convidar, editar permissões e desativar quem sai.",
        path: "/settings/users",
      },
      {
        label: "Metas",
        description: "Pontuação mensal por colaborador e metas do time.",
        path: "/settings/goals",
      },
      {
        label: "Notificações",
        description: "Quais eventos avisam, e por onde.",
        path: "/settings/notifications",
      },
      {
        label: "Dados da conta",
        description: "Razão social, logo e dados de cobrança.",
        path: "/subscription/account",
      },
    ],
  },
  {
    title: "Cadastros",
    links: [
      {
        label: "Origens de contato",
        description: "De onde vêm os clientes — usado no funil e nos relatórios.",
        path: "/settings/origins",
      },
      {
        label: "Tipos de tarefa",
        description: "O catálogo de atividades e a pontuação de cada uma.",
        path: "/settings/task-types",
      },
    ],
  },
  {
    title: "Processos",
    links: [
      {
        label: "Grupos de ação",
        description: "As áreas do escritório: cível, trabalhista, previdenciário…",
        path: "/settings/action-groups",
      },
      {
        label: "Tipos de ação",
        description: "As ações dentro de cada grupo.",
        path: "/settings/lawsuit-types",
      },
      {
        label: "Etapas",
        description: "As fases pelas quais um processo caminha.",
        path: "/settings/stages",
      },
      {
        label: "Fluxos de trabalho",
        description: "Sequências de tarefas aplicadas a um processo de uma vez.",
        path: "/settings/workflows",
      },
      {
        label: "Termos monitorados",
        description: "Nomes e OABs vigiados no Diário Oficial.",
        path: "/settings/monitored-terms",
      },
    ],
  },
  {
    title: "Financeiro",
    links: [
      {
        label: "Plano de contas",
        description: "Categorias, centros de custo, contas e cartões.",
        path: "/settings/financial",
        capability: "financial.read",
      },
    ],
  },
  {
    title: "Automação",
    links: [
      {
        label: "Automações",
        description: "Gatilhos que criam tarefas e avisam pessoas sozinhos.",
        path: "/settings/automations",
      },
      {
        label: "Webhooks",
        description: "Avisar outro sistema quando algo acontece aqui.",
        path: "/settings/webhooks",
      },
      {
        label: "API",
        description: "Tokens de acesso à API pública.",
        path: "/settings/api",
      },
      {
        label: "Integrações",
        description: "Saúde da sincronização com DJEN e DataJud.",
        path: "/settings/integrations",
      },
    ],
  },
  {
    title: "Inteligência artificial",
    links: [
      {
        label: "IA",
        description: "Qual modelo cada recurso usa, e o teto de gasto.",
        path: "/settings/ai",
      },
    ],
  },
];
