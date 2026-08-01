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
    path: "/subscription",
    icon: CreditCard,
    capability: "settings.manage",
  },
  { label: "Suporte", icon: LifeBuoy },
  { label: "Indicar o Rito", icon: Share2 },
];

export const ROUTABLE_NAV_ITEMS = NAV_ITEMS.filter(
  (item): item is NavItem & { path: string } => item.path !== undefined,
);
