import { useMutation } from "@tanstack/react-query";
import * as React from "react";

import { DataTable } from "@/components/domain/DataTable";
import type { DataTableColumn } from "@/components/domain/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { askMetrics, runMetrics, type AskResult } from "@/features/reports/insights";
import { SqlPreview } from "@/features/reports/SqlPreview";
import { ApiError } from "@/lib/errors";

type Row = Record<string, unknown>;

/** Perguntar métrica em português (spec 089 §7).
 *
 * Duas etapas de propósito: a IA propõe a consulta, a pessoa confere e manda rodar. */
export function AskMetricsBox(): JSX.Element {
  const [question, setQuestion] = React.useState("");
  const [proposal, setProposal] = React.useState<AskResult | null>(null);
  const [result, setResult] = React.useState<AskResult | null>(null);
  const [clarification, setClarification] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const ask = useMutation({
    mutationFn: () => askMetrics(question),
    onSuccess: (data) => {
      setProposal(data);
      setResult(null);
      setClarification(null);
      setError(null);
    },
    onError: (exc: unknown) => {
      setProposal(null);
      if (exc instanceof ApiError) {
        const duvida = exc.extensions.clarification;
        if (typeof duvida === "string") {
          setClarification(duvida);
          return;
        }
        setError(exc.message);
        return;
      }
      setError("Não foi possível interpretar a pergunta.");
    },
  });

  const run = useMutation({
    mutationFn: () => runMetrics(question, proposal!.sql),
    onSuccess: (data) => {
      setResult(data);
      setProposal(null);
    },
    onError: () => setError("A consulta não pôde ser executada."),
  });

  const columns: DataTableColumn<Row>[] = (result?.columns ?? []).map((name) => ({
    id: name,
    header: name,
    cell: (row) => String(row[name] ?? "—"),
  }));

  return (
    <section className="space-y-3" aria-label="Perguntar sobre os indicadores">
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          ask.mutate();
        }}
      >
        <Input
          aria-label="Pergunte sobre os indicadores"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ex.: quantos processos foram fechados por mês este ano?"
        />
        <Button type="submit" disabled={ask.isPending || question.trim().length < 3}>
          Perguntar
        </Button>
      </form>

      {clarification && (
        <p role="status" className="rounded border border-warning bg-warning/10 p-2 text-sm">
          A IA precisa de um esclarecimento: {clarification}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {proposal && (
        <SqlPreview
          sql={proposal.sql}
          relations={proposal.relations}
          touchesFinancial={proposal.touches_financial}
          isRunning={run.isPending}
          onRun={() => run.mutate()}
          onCancel={() => setProposal(null)}
        />
      )}

      {result && (
        <div className="space-y-2">
          <p className="text-sm text-primary">{result.summary}</p>
          <DataTable
            columns={columns}
            data={result.rows as Row[]}
            getRowId={(row) => JSON.stringify(row)}
            emptyMessage="A consulta não devolveu nenhuma linha."
          />
        </div>
      )}
    </section>
  );
}
