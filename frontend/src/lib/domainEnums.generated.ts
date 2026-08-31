// GERADO por backend/scripts/dump_enums.py — não edite à mão.
// Fonte de verdade: os StrEnum de `backend/app/domain/**`. Regenerar:
//   cd backend && uv run python -m scripts.dump_enums
// O meta-teste `tests/meta/test_enum_mirror.py` falha se este arquivo sair de sincronia.

export type AccountKind = "CORRENTE" | "POUPANCA" | "INVESTIMENTO" | "CARTAO_CREDITO" | "OUTRO";

export type AccountPlan = "ESSENCIAL" | "BANCA_JURIDICA" | "BANCA_MAX" | "ELITE";

export type ContingencyLevel = "PROVAVEL" | "POSSIVEL" | "REMOTA";

export type CourtSegment = "ESTADUAL" | "FEDERAL" | "TRABALHO" | "ELEITORAL" | "MILITAR" | "SUPERIOR" | "CONTAS" | "CONSELHO";

export type DocumentScopeType = "CUSTOMER" | "LAWSUIT";

export type DunningChannel = "EMAIL" | "SMS" | "WHATSAPP";

export type DunningStatus = "SENT" | "FAILED" | "SKIPPED";

export type EntryType = "RECEITA" | "DESPESA";

export type FinancialAccess = "NONE" | "READ_ONLY" | "FULL";

export type FinancialRecurrence = "MENSAL" | "BIMESTRAL" | "TRIMESTRAL" | "SEMESTRAL" | "ANUAL";

export type LawsuitOutcome = "GANHO" | "PERDIDO" | "ACORDO";

export type MovementOrigin = "TRIBUNAL" | "MANUAL";

export type PartnershipStatus = "PENDENTE" | "ATIVA" | "RECUSADA" | "ENCERRADA";

export type PartyPole = "ATIVO" | "PASSIVO" | "CONTRARIA" | "TERCEIRO";

export type PersonType = "PF" | "PJ";

export type RecurrencePeriod = "DIARIA" | "SEMANAL" | "QUINZENAL" | "MENSAL" | "BIMESTRAL" | "TRIMESTRAL" | "SEMESTRAL" | "ANUAL";

export type RecurrenceWeek = "DIA_EXATO" | "PRIMEIRA" | "SEGUNDA" | "TERCEIRA" | "ULTIMA";

export type TaskComplexity = "SIMPLES" | "MEDIA" | "MEDIA_ALTA" | "ALTA" | "ALTISSIMA";

export type TaskDuration = "MIN_8" | "MIN_15" | "MIN_30" | "HOUR_1" | "HOUR_2_PLUS";

export type TemplateType = "CONTRATO" | "PETICAO" | "RECURSO" | "DOCUMENTO";

export type TermKind = "OAB" | "CPF" | "CNPJ";

export type TermStatus = "PENDENTE" | "SINCRONIZANDO" | "ATIVO" | "FALHA" | "PAUSADO";

export type TransactionKind = "RECEITA" | "DESPESA" | "TRANSFERENCIA";

export type UserRole = "GESTOR" | "ADMINISTRADOR" | "COLABORADOR";
