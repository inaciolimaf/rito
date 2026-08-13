import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import {
  listNotificationPreferences,
  listNotificationRules,
  updateNotificationPreference,
  updateNotificationRule,
  type NotificationChannel,
  type NotificationEvent,
} from "@/features/notifications/api";
import { listUsers } from "@/features/users/api";
import { useAuth } from "@/providers/AuthProvider";

const EVENT_LABELS: Record<NotificationEvent, string> = {
  NOVO_CLIENTE: "Novo contato",
  NOVO_PROCESSO: "Novo processo",
  INTIMACAO: "Intimação roteada",
};

const CHANNELS: { value: NotificationChannel; label: string }[] = [
  { value: "EMAIL", label: "E-mail" },
  { value: "SMS", label: "SMS" },
  { value: "WHATSAPP", label: "WhatsApp" },
];

/** /settings/notifications (spec 069 §6) — regras por evento (Gestor) + preferências
 * de canal (qualquer usuário), sem aba: volume baixo demais para justificar. */
export function NotificationSettingsPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";

  return (
    <div className="space-y-8 p-6">
      <h1 className="text-lg font-semibold text-primary">Notificações</h1>
      {isGestor && <NotificationRulesSection />}
      <NotificationPreferencesSection />
    </div>
  );
}

function NotificationRulesSection(): JSX.Element {
  const queryClient = useQueryClient();
  const { data: rules } = useQuery({
    queryKey: ["notification-rules"],
    queryFn: listNotificationRules,
  });
  const { data: usersPage } = useQuery({
    queryKey: ["users", "for-notification-rules"],
    queryFn: () => listUsers({ limit: 100 }),
  });
  const users = usersPage?.items ?? [];
  const [feedback, setFeedback] = React.useState<string | null>(null);

  const saveRule = useMutation({
    mutationFn: ({
      event,
      responsibleUserId,
      channels,
    }: {
      event: NotificationEvent;
      responsibleUserId: string | null;
      channels: NotificationChannel[];
    }) => updateNotificationRule(event, { responsible_user_id: responsibleUserId, channels }),
    onSuccess: async () => {
      setFeedback("Regra salva.");
      await queryClient.invalidateQueries({ queryKey: ["notification-rules"] });
    },
  });

  async function searchUsers(query: string): Promise<EntityOption[]> {
    const page = await listUsers({ q: query, limit: 20 });
    return page.items.map((item) => ({ id: item.id, label: item.name }));
  }

  return (
    <section aria-label="Regras por evento" className="space-y-4">
      <div>
        <h2 className="text-base font-semibold text-primary">Regras por evento</h2>
        <p className="text-sm text-muted">
          Quem é avisado quando o evento acontece, e por quais canais além do sino.
        </p>
      </div>
      <ul className="space-y-4">
        {(rules ?? []).map((rule) => {
          const responsible: EntityOption[] = rule.responsible_user_id
            ? (() => {
                const found = users.find((item) => item.id === rule.responsible_user_id);
                return found ? [{ id: found.id, label: found.name }] : [];
              })()
            : [];

          return (
            <li key={rule.event} className="space-y-2 rounded border border-default p-4">
              <h3 className="text-sm font-medium text-primary">{EVENT_LABELS[rule.event]}</h3>
              <EntityPicker
                label={`Responsável por ${EVENT_LABELS[rule.event]}`}
                placeholder="Buscar usuário..."
                value={responsible}
                onSearch={searchUsers}
                onChange={(next) =>
                  saveRule.mutate({
                    event: rule.event,
                    responsibleUserId: next[0]?.id ?? null,
                    channels: rule.channels,
                  })
                }
              />
              <div className="flex items-center gap-4">
                {CHANNELS.map((channel) => (
                  <label
                    key={channel.value}
                    className="flex items-center gap-2 text-sm text-primary"
                  >
                    <Checkbox
                      checked={rule.channels.includes(channel.value)}
                      onCheckedChange={(checked) =>
                        saveRule.mutate({
                          event: rule.event,
                          responsibleUserId: rule.responsible_user_id,
                          channels:
                            checked === true
                              ? [...rule.channels, channel.value]
                              : rule.channels.filter((item) => item !== channel.value),
                        })
                      }
                    />
                    {channel.label}
                  </label>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
      {feedback && (
        <p role="status" className="text-sm text-accent">
          {feedback}
        </p>
      )}
    </section>
  );
}

function NotificationPreferencesSection(): JSX.Element {
  const queryClient = useQueryClient();
  const { data: preferences } = useQuery({
    queryKey: ["notification-preferences"],
    queryFn: listNotificationPreferences,
  });

  const savePreference = useMutation({
    mutationFn: ({ channel, enabled }: { channel: NotificationChannel; enabled: boolean }) =>
      updateNotificationPreference(channel, enabled),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["notification-preferences"] });
    },
  });

  return (
    <section aria-label="Minhas preferências" className="space-y-3">
      <div>
        <h2 className="text-base font-semibold text-primary">Minhas preferências</h2>
        <p className="text-sm text-muted">
          Desligue um canal para não receber notificações por ele — o sino sempre recebe.
        </p>
      </div>
      <ul className="space-y-2">
        {(preferences ?? []).map((preference) => (
          <li key={preference.channel} className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-primary">
              <Checkbox
                checked={preference.enabled}
                onCheckedChange={(checked) =>
                  savePreference.mutate({
                    channel: preference.channel,
                    enabled: checked === true,
                  })
                }
              />
              {CHANNELS.find((item) => item.value === preference.channel)?.label ??
                preference.channel}
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}
