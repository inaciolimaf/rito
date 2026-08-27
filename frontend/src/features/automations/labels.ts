import type { ActionKind, DelayKind, TriggerKind } from "@/features/automations/api";

/** Os rótulos ficam num arquivo só porque aparecem em quatro telas — builder, lista,
 * simulação e histórico — e um gatilho chamado de dois jeitos diferentes faz o usuário
 * achar que são dois gatilhos. */
export const TRIGGER_LABELS: Record<TriggerKind, string> = {
  "task.completed": "Quando uma tarefa for concluída",
  "lawsuit.stage_changed": "Quando o processo mudar de etapa",
  "lawsuit.created": "Quando um processo for cadastrado",
  "publication.received": "Quando chegar uma intimação",
  "transaction.overdue": "Quando um lançamento vencer",
};

export const ACTION_LABELS: Record<ActionKind, string> = {
  create_task: "Criar tarefa",
  set_assignee: "Definir responsável",
  change_stage: "Mudar de etapa",
  notify: "Notificar",
  wait_condition: "Aguardar condição",
  http_request: "Enviar webhook",
  llm_decision: "Decidir com IA",
};

export const DELAY_LABELS: Record<DelayKind, string> = {
  immediate: "Imediatamente",
  business_days: "Depois de N dias úteis",
  calendar_days: "Depois de N dias corridos",
  after_previous: "Quando a ação anterior for concluída",
};

export const STATUS_LABELS: Record<string, string> = {
  running: "Em execução",
  waiting: "Aguardando",
  done: "Concluída",
  failed: "Falhou",
  skipped: "Pulada",
};
