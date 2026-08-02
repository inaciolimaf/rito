import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import type { UseFormReturn } from "react-hook-form";

import { CourtSelect } from "@/features/courts/CourtSelect";
import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { listActionGroups } from "@/features/action-groups/api";
import { listCourtSystems } from "@/features/courts/api";
import { listLawsuitTypes } from "@/features/lawsuit-types/api";
import { PartySelector } from "@/features/lawsuits/PartySelector";
import { StageStepSelect } from "@/features/lawsuits/StageStepSelect";
import type { LawsuitFormValues } from "@/features/lawsuits/schema";

const SELECT_CLASS =
  "h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export interface LawsuitFormProps {
  form: UseFormReturn<LawsuitFormValues>;
  onSearchUsers: (query: string) => Promise<EntityOption[]>;
  onSearchCustomers: (query: string) => Promise<EntityOption[]>;
  currentResponsible: EntityOption | null;
  currentCourt: EntityOption | null;
  /** Grupo/fase da seleção atual (spec 022 §6) — não são campos do formulário (o processo
   * guarda só `lawsuit_type_id`/`stage_id`), só o estado inicial dos filtros em cascata. */
  initialGroupId?: string | null;
  initialStepId?: number | null;
}

/** Tipo de ação e etapa são escolhidos por cascata (regra: grupo filtra tipo, fase filtra
 * etapa) — grupo e fase são estado local, nunca enviados ao servidor (regra 2: são
 * derivados, `action_group_id`/`step_id` não existem no payload). */
export function LawsuitForm({
  form,
  onSearchUsers,
  onSearchCustomers,
  currentResponsible,
  currentCourt,
  initialGroupId,
  initialStepId,
}: LawsuitFormProps): JSX.Element {
  const {
    register,
    watch,
    setValue,
    formState: { errors },
  } = form;

  const [groupId, setGroupId] = React.useState(initialGroupId ?? "");
  React.useEffect(() => {
    if (initialGroupId) setGroupId(initialGroupId);
  }, [initialGroupId]);

  const userId = watch("user_id");
  const stageId = watch("stage_id");
  const courtId = watch("court_id");
  const parties = watch("parties");

  const { data: groupsPage } = useQuery({
    queryKey: ["action-groups", "for-lawsuit-form"],
    queryFn: () => listActionGroups({ status: "active" }),
  });
  const groups = groupsPage?.items ?? [];

  const { data: typesPage } = useQuery({
    queryKey: ["lawsuit-types", "for-lawsuit-form", groupId],
    queryFn: () => listLawsuitTypes({ group_id: groupId, status: "active" }),
    enabled: groupId !== "",
  });
  const types = typesPage?.items ?? [];

  const { data: courtSystems = [] } = useQuery({
    queryKey: ["court-systems"],
    queryFn: listCourtSystems,
  });

  const selectedResponsible: EntityOption[] =
    userId && currentResponsible?.id === userId ? [currentResponsible] : [];
  const selectedCourt: EntityOption[] =
    courtId && currentCourt?.id === courtId ? [currentCourt] : [];

  return (
    <>
      <div className="space-y-1">
        <Label htmlFor="lawsuit-responsible">Responsável</Label>
        <EntityPicker
          value={selectedResponsible}
          onChange={(next) => setValue("user_id", next[0]?.id ?? "", { shouldDirty: true })}
          onSearch={onSearchUsers}
          label="Responsável"
          placeholder="Buscar usuário..."
        />
        {errors.user_id && <p className="text-sm text-danger">{errors.user_id.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="lawsuit-group">Grupo de ação</Label>
          <select
            id="lawsuit-group"
            className={SELECT_CLASS}
            value={groupId}
            onChange={(event) => {
              setGroupId(event.target.value);
              setValue("lawsuit_type_id", "", { shouldDirty: true });
            }}
          >
            <option value="">Selecione</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <Label htmlFor="lawsuit-type">Tipo de ação</Label>
          {groupId === "" ? (
            <p className="text-sm text-muted">Selecione um grupo primeiro.</p>
          ) : (
            <select id="lawsuit-type" className={SELECT_CLASS} {...register("lawsuit_type_id")}>
              <option value="">Selecione</option>
              {types.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name}
                </option>
              ))}
            </select>
          )}
          {errors.lawsuit_type_id && (
            <p className="text-sm text-danger">{errors.lawsuit_type_id.message}</p>
          )}
        </div>
      </div>

      <StageStepSelect
        value={stageId}
        onChange={(next) => setValue("stage_id", next, { shouldDirty: true })}
        initialStepId={initialStepId}
      />
      {errors.stage_id && <p className="text-sm text-danger">{errors.stage_id.message}</p>}

      <PartySelector
        value={parties}
        onChange={(next) => setValue("parties", next, { shouldDirty: true, shouldValidate: true })}
        onSearch={onSearchCustomers}
      />
      {errors.parties && <p className="text-sm text-danger">{errors.parties.message}</p>}

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <CourtSelect
            value={selectedCourt}
            onChange={(next) => setValue("court_id", next[0]?.id ?? "", { shouldDirty: true })}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="lawsuit-court-system">Sistema processual</Label>
          <select
            id="lawsuit-court-system"
            className={SELECT_CLASS}
            {...register("court_system_id")}
          >
            <option value="">Selecione</option>
            {courtSystems.map((system) => (
              <option key={system.id} value={system.id}>
                {system.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="process_number">Número do processo</Label>
          <Input id="process_number" {...register("process_number")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="protocol_number">Protocolo</Label>
          <Input id="protocol_number" {...register("protocol_number")} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="originating_process">Processo originário</Label>
          <Input id="originating_process" {...register("originating_process")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="folder">Pasta</Label>
          <Input id="folder" maxLength={30} {...register("folder")} />
          {errors.folder && <p className="text-sm text-danger">{errors.folder.message}</p>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="filing_year">Ano de distribuição</Label>
          <Input id="filing_year" type="number" {...register("filing_year")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="process_date">Data do processo</Label>
          <Input id="process_date" type="date" {...register("process_date")} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="judiciary">Justiça</Label>
          <Input id="judiciary" {...register("judiciary")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="county">Comarca</Label>
          <Input id="county" {...register("county")} />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="court_division">Vara</Label>
        <Input id="court_division" {...register("court_division")} />
      </div>

      <div className="space-y-1">
        <Label htmlFor="notes">Anotações</Label>
        <textarea
          id="notes"
          className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          rows={3}
          {...register("notes")}
        />
      </div>
    </>
  );
}
