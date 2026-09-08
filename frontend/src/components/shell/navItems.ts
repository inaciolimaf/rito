import {
  BarChart3,
  Bell,
  BookOpen,
  Calendar,
  CreditCard,
  Gavel,
  Handshake,
  Home,
  KanbanSquare,
  LifeBuoy,
  ListTodo,
  Settings,
  Share2,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  /** Ausente => item abre modal (Suporte, Indicar), não navega (spec 008, seção 6). */
  path?: string;
  icon: LucideIcon;
  /** Ausente => visível para qualquer usuário autenticado. */
  capability?: string;
}

/** Os 15 itens do menu lateral do ADVBOX — 13 navegam, 2 abrem modal (docs/ADVBOX-ESPECIFICACAO-COMPLETA.md). */
export const NAV_ITEMS: NavItem[] = [
  { label: "Meu Painel", path: "/home", icon: Home },
  { label: "Agenda", path: "/schedules", icon: Calendar },
  { label: "Atividades", path: "/posts", icon: ListTodo },
  { label: "CRM", path: "/crm", icon: KanbanSquare },
  { label: "Contatos", path: "/customers", icon: Users },
  { label: "Processos", path: "/lawsuits", icon: Gavel },
  { label: "Intimações", path: "/publications", icon: Bell },
  { label: "Parceiros", path: "/partners", icon: Handshake },
  { label: "Modelos", path: "/library", icon: BookOpen },
  { label: "Financeiro", path: "/transactions", icon: Wallet, capability: "financial.read" },
  { label: "Relatórios", path: "/reports", icon: BarChart3 },
  { label: "Configurações", path: "/settings", icon: Settings, capability: "settings.manage" },
  {
    label: "Conta e assinatura",
    // Só "Dados da conta" existe até aqui (spec 011) — plano/assinatura é fora do clone
    // (CLAUDE.md, spec 011 seção 3), então o item já aponta direto pro sub-caminho real.
    path: "/subscription/account",
    icon: CreditCard,
    capability: "settings.manage",
  },
  { label: "Suporte", icon: LifeBuoy },
  { label: "Indicar o Rito", icon: Share2 },
];

export const ROUTABLE_NAV_ITEMS = NAV_ITEMS.filter(
  (item): item is NavItem & { path: string } => item.path !== undefined,
);

/** A capability exigida por uma rota, ou `null` quando qualquer autenticado entra.
 *
 * Spec 138, regra 9: as `capabilities` do `/auth/me` só escondiam itens de menu. Como os
 * filtros vivem na URL e o link é compartilhável por desenho (CLAUDE.md §6), receber o
 * link do financeiro sem ter acesso a ele é rotina — e o que aparecia era erro genérico
 * (ou o carregando eterno da regra 4), nunca "você não tem acesso a esta área". O casamento
 * é por prefixo de caminho: `/settings/users` herda a exigência de `/settings`. */
export function requiredCapabilityFor(pathname: string): string | null {
  const match = NAV_ITEMS.filter((item) => item.capability && item.path)
    .filter((item) => pathname === item.path || pathname.startsWith(`${item.path}/`))
    // O caminho mais específico manda: se algum dia `/settings/x` exigir outra coisa
    // além do que `/settings` exige, é a dele que vale.
    .sort((a, b) => (b.path?.length ?? 0) - (a.path?.length ?? 0))[0];
  return match?.capability ?? null;
}
