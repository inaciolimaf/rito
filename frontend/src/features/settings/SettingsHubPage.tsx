import { Link } from "react-router-dom";

import { EmptyState } from "@/components/domain/EmptyState";
import { SETTINGS_SECTIONS } from "@/features/settings/settingsSections";
import { useAuth } from "@/providers/AuthProvider";

/** Spec 102, regra 16: o destino que `navItems.ts` já apontava desde a spec 008. */
export function SettingsHubPage(): JSX.Element {
  const { user } = useAuth();
  const capabilities = user?.capabilities ?? [];

  // Cada grupo esconde o que o perfil não pode ver — a MESMA capability que já filtra o
  // item na sidebar. Um grupo que fica sem nenhum link não é renderizado vazio.
  const sections = SETTINGS_SECTIONS.map((section) => ({
    ...section,
    links: section.links.filter(
      (link) => !link.capability || capabilities.includes(link.capability),
    ),
  })).filter((section) => section.links.length > 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-primary">Configurações</h1>
        <p className="text-sm text-secondary">
          Tudo o que muda o comportamento do escritório, num lugar só.
        </p>
      </div>

      {sections.length === 0 ? (
        <EmptyState
          title="Nada por aqui"
          description="Seu perfil não tem acesso a nenhuma configuração."
        />
      ) : (
        sections.map((section) => (
          <section key={section.title} className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary">
              {section.title}
            </h2>
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {section.links.map((link) => (
                <li key={link.path}>
                  <Link
                    to={link.path}
                    className="block h-full rounded border border-default bg-surface p-4 transition hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    <span className="block text-sm font-medium text-primary">{link.label}</span>
                    <span className="mt-1 block text-sm text-secondary">{link.description}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
