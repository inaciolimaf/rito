import * as React from "react";
import { z } from "zod";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  ConfirmDialog,
  DataTable,
  EmptyState,
  EntityPicker,
  FilterBar,
  FormModal,
  StatCard,
  useDataTable,
  useFilters,
  type DataTableColumn,
  type EntityOption,
  type FilterFieldDef,
} from "@/components/domain";

interface Contact {
  id: string;
  name: string;
  city: string;
  active: boolean;
}

const ALL_CONTACTS: Contact[] = [
  { id: "1", name: "Ana Souza", city: "São Paulo", active: true },
  { id: "2", name: "Bruno Lima", city: "Rio de Janeiro", active: true },
  { id: "3", name: "Carla Dias", city: "Belo Horizonte", active: false },
  { id: "4", name: "Diego Alves", city: "São Paulo", active: true },
];

const filterFields: FilterFieldDef[] = [
  { key: "q", label: "Buscar", type: "text" },
  {
    key: "city",
    label: "Cidade",
    type: "select",
    options: [
      { value: "São Paulo", label: "São Paulo" },
      { value: "Rio de Janeiro", label: "Rio de Janeiro" },
      { value: "Belo Horizonte", label: "Belo Horizonte" },
    ],
  },
];

const contactSchema = z.object({
  name: z.string().min(1, "Nome é obrigatório."),
});

async function fakeSearchContacts(query: string): Promise<EntityOption[]> {
  await new Promise((resolve) => setTimeout(resolve, 50));
  return ALL_CONTACTS.filter((contact) =>
    contact.name.toLowerCase().includes(query.toLowerCase()),
  ).map((contact) => ({ id: contact.id, label: contact.name, description: contact.city }));
}

const columns: DataTableColumn<Contact>[] = [
  { id: "name", header: "Nome", cell: (row) => row.name, sortable: true },
  { id: "city", header: "Cidade", cell: (row) => row.city, sortable: true },
  {
    id: "active",
    header: "Status",
    cell: (row) => (row.active ? "Ativo" : "Arquivado"),
  },
];

export function KitchenSinkPage(): JSX.Element {
  const { values } = useFilters(filterFields);
  const { sort, toggleSort, selectedIds, setSelectedIds } = useDataTable();
  const [page, setPage] = React.useState(0);
  const [isFormOpen, setIsFormOpen] = React.useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = React.useState(false);
  const [pickerValue, setPickerValue] = React.useState<EntityOption[]>([]);
  const pageSize = 2;

  const filtered = React.useMemo(() => {
    let result = ALL_CONTACTS;
    if (typeof values.q === "string" && values.q) {
      result = result.filter((contact) =>
        contact.name.toLowerCase().includes(values.q!.toString().toLowerCase()),
      );
    }
    if (typeof values.city === "string" && values.city) {
      result = result.filter((contact) => contact.city === values.city);
    }
    if (sort) {
      result = [...result].sort((a, b) => {
        const left = String(a[sort.field as keyof Contact]);
        const right = String(b[sort.field as keyof Contact]);
        return sort.order === "asc" ? left.localeCompare(right) : right.localeCompare(left);
      });
    }
    return result;
  }, [values, sort]);

  const paged = filtered.slice(page * pageSize, page * pageSize + pageSize);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8 p-8">
      <h1 className="text-xl font-semibold text-primary">Kitchen sink — design system</h1>

      <section className="flex gap-4">
        <StatCard label="Contatos ativos" value={3} previousValue={2} />
        <StatCard label="Arquivados" value={1} previousValue={1} />
        <StatCard label="Carregando" value={0} isLoading />
      </section>

      <section className="flex flex-col gap-3">
        <FilterBar fields={filterFields} />

        <DataTable
          columns={columns}
          data={paged}
          getRowId={(row) => row.id}
          sort={sort}
          onSortChange={toggleSort}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          bulkActions={[{ label: "Arquivar selecionados", onClick: () => setIsConfirmOpen(true) }]}
          onExport={() => undefined}
          pagination={{
            hasNextPage: (page + 1) * pageSize < filtered.length,
            hasPreviousPage: page > 0,
            onNextPage: () => setPage((current) => current + 1),
            onPreviousPage: () => setPage((current) => Math.max(0, current - 1)),
          }}
        />

        <Button type="button" onClick={() => setIsFormOpen(true)} className="w-fit">
          Novo contato
        </Button>
      </section>

      <section>
        <EmptyState
          title="Nenhuma tarefa pendente"
          description="Quando houver algo para revisar, aparece aqui."
          action={{ label: "Criar tarefa", onClick: () => undefined }}
        />
      </section>

      <section className="flex flex-col gap-1">
        <Label htmlFor="kitchen-sink-picker">Vincular contato</Label>
        <EntityPicker
          value={pickerValue}
          onChange={setPickerValue}
          onSearch={fakeSearchContacts}
          label="Vincular contato"
        />
      </section>

      <FormModal
        open={isFormOpen}
        onOpenChange={setIsFormOpen}
        title="Novo contato"
        schema={contactSchema}
        defaultValues={{ name: "" }}
        onSubmit={async () => {
          setIsFormOpen(false);
        }}
      >
        {(form) => (
          <div className="space-y-1">
            <Label htmlFor="contact-name">Nome</Label>
            <Input id="contact-name" {...form.register("name")} />
          </div>
        )}
      </FormModal>

      <ConfirmDialog
        open={isConfirmOpen}
        onOpenChange={setIsConfirmOpen}
        title="Arquivar contatos selecionados?"
        destructive
        onConfirm={() => setSelectedIds(new Set())}
      />
    </div>
  );
}
