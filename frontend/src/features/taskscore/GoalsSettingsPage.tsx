import { GoalsSettingsForm } from "@/features/taskscore/GoalsSettingsForm";

/** /settings/goals (spec 039 §6) — configuração de metas; escrita exige GESTOR na API
 * (o link de Configurações já só aparece para quem tem settings.manage). */
export function GoalsSettingsPage(): JSX.Element {
  return (
    <div className="space-y-4 p-6">
      <h1 className="text-lg font-semibold text-primary">Metas</h1>
      <GoalsSettingsForm />
    </div>
  );
}
