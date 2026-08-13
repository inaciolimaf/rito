import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { EmptyState } from "@/components/domain/EmptyState";
import { AccountForm } from "@/features/account/AccountForm";
import { AccountStorageSection } from "@/features/account/AccountStorageSection";
import { LogoUploader } from "@/features/account/LogoUploader";
import {
  getAccount,
  updateAccount,
  uploadAccountLogo,
  type AccountData,
} from "@/features/account/api";
import { DEFAULT_ACCOUNT_VALUES, type AccountFormValues } from "@/features/account/schema";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

const ACCOUNT_QUERY_KEY = ["account"];

export function AccountPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";
  const queryClient = useQueryClient();
  const [serverError, setServerError] = React.useState<ApiError | null>(null);

  const { data: account, isLoading } = useQuery({
    queryKey: ACCOUNT_QUERY_KEY,
    queryFn: getAccount,
  });

  const updateMutation = useMutation({
    mutationFn: updateAccount,
    onSuccess: (data: AccountData) => {
      queryClient.setQueryData(ACCOUNT_QUERY_KEY, data);
      setServerError(null);
    },
    onError: (error: unknown) => {
      setServerError(error instanceof ApiError ? error : null);
    },
  });

  const logoMutation = useMutation({
    mutationFn: uploadAccountLogo,
    onSuccess: (data: AccountData) => {
      queryClient.setQueryData(ACCOUNT_QUERY_KEY, data);
    },
  });

  if (isLoading) {
    return <p className="p-6 text-sm text-muted">Carregando...</p>;
  }

  if (!account && !isGestor) {
    return (
      <div className="p-6">
        <EmptyState
          title="Conta ainda não configurada"
          description="Peça a um Gestor para preencher os dados do escritório."
        />
      </div>
    );
  }

  const defaultValues: AccountFormValues = account
    ? { ...account, site: account.site ?? "" }
    : DEFAULT_ACCOUNT_VALUES;

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-lg font-semibold text-primary">Dados da conta</h1>
        <p className="text-sm text-muted">
          Informações do escritório usadas nos documentos e modelos.
        </p>
      </div>

      {account && <AccountStorageSection disabled={!isGestor} />}

      {account && (
        <LogoUploader
          logoUrl={account.logo_url}
          disabled={!isGestor}
          onUpload={async (file) => {
            await logoMutation.mutateAsync(file);
          }}
        />
      )}

      <AccountForm
        defaultValues={defaultValues}
        disabled={!isGestor}
        serverError={serverError}
        onSubmit={async (values) => {
          await updateMutation.mutateAsync(values);
        }}
      />
    </div>
  );
}
