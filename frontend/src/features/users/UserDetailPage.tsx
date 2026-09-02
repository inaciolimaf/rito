import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { useParams } from "react-router-dom";

import { EmptyState } from "@/components/domain/EmptyState";
import { ImageUploader } from "@/components/domain/ImageUploader";
import {
  getOccupations,
  getUser,
  updateUser,
  uploadUserAvatar,
  type UserData,
} from "@/features/users/api";
import { apiTimeToInput, apiDurationToInput } from "@/features/users/timeFormat";
import { UserForm } from "@/features/users/UserForm";
import type { UserFormValues } from "@/features/users/schema";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

function toFormValues(data: UserData): UserFormValues {
  return {
    name: data.name,
    role: data.role as UserFormValues["role"],
    financial_access: data.financial_access as UserFormValues["financial_access"],
    occupation_id: data.occupation_id != null ? String(data.occupation_id) : "",
    identification: data.identification ?? "",
    document: data.document ?? "",
    birthdate: data.birthdate ?? "",
    number_ctps: data.number_ctps ?? "",
    number_oab: data.number_oab ?? "",
    cellphone: data.cellphone ?? "",
    phone: data.phone ?? "",
    salary: data.salary ?? "",
    admission_date: data.admission_date ?? "",
    resignation_date: data.resignation_date ?? "",
    workStart: apiTimeToInput(data.work_start),
    workInterval: apiDurationToInput(data.work_interval),
    workEnd: apiTimeToInput(data.work_end),
    points_goal: data.points_goal != null ? String(data.points_goal) : "",
    report_deadline: data.report_deadline,
    report_deleted: data.report_deleted,
    is_responsible: data.is_responsible,
  };
}

export function UserDetailPage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = React.useState<ApiError | null>(null);

  const {
    data: targetUser,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["users", id],
    queryFn: () => getUser(id as string),
    enabled: Boolean(id),
  });

  const { data: occupations = [] } = useQuery({
    queryKey: ["occupations"],
    queryFn: getOccupations,
  });

  const updateMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => updateUser(id as string, values),
    onSuccess: (data) => {
      queryClient.setQueryData(["users", id], data);
      setServerError(null);
    },
    onError: (mutationError: unknown) => {
      setServerError(mutationError instanceof ApiError ? mutationError : null);
    },
  });

  const avatarMutation = useMutation({
    mutationFn: (file: File) => uploadUserAvatar(id as string, file),
    onSuccess: (data) => {
      queryClient.setQueryData(["users", id], data);
    },
  });

  if (isLoading) {
    return <p className="p-6 text-sm text-muted">Carregando...</p>;
  }

  if (error || !targetUser) {
    return (
      <div className="p-6">
        <EmptyState
          title="Não foi possível carregar este usuário."
          description={error instanceof ApiError ? error.message : undefined}
          role="alert"
        />
      </div>
    );
  }

  const isSelf = currentUser?.id === targetUser.id;

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-lg font-semibold text-primary">{targetUser.name}</h1>

      <ImageUploader
        label="Foto de perfil"
        imageUrl={targetUser.avatar_url}
        alt="Foto de perfil"
        emptyLabel="Sem foto"
        uploadLabel="Enviar foto"
        replaceLabel="Trocar foto"
        replaceTitle="Substituir foto?"
        replaceDescription="A foto atual será substituída pelo novo arquivo."
        oversizeError="Foto acima de 2 MB."
        uploadError="Não foi possível enviar a foto."
        shape="circle"
        onUpload={async (file) => {
          await avatarMutation.mutateAsync(file);
        }}
      />

      <UserForm
        defaultValues={toFormValues(targetUser)}
        occupations={occupations}
        canEditRoleAndFinancial={!isSelf}
        serverError={serverError}
        onSubmit={async (values) => {
          await updateMutation.mutateAsync(values);
        }}
      />
    </div>
  );
}
