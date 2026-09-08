import { describe, expect, it } from "vitest";

import { isValidCnpj, isValidCpf } from "@/lib/br-documents";

// Espelho de `backend/app/core/br_documents.py`: os mesmos casos que o teste do backend
// cobre precisam dar o mesmo veredicto aqui — é o ponto de a validação existir nos dois.
describe("br-documents (spec 138, regra 7)", () => {
  it("aceita CPF e CNPJ com dígito verificador correto", () => {
    expect(isValidCpf("529.982.247-25")).toBe(true);
    expect(isValidCpf("52998224725")).toBe(true);
    expect(isValidCnpj("11.222.333/0001-81")).toBe(true);
  });

  it("recusa dígito verificador errado — o que o front só via como '11 dígitos'", () => {
    expect(isValidCpf("52998224726")).toBe(false);
    expect(isValidCnpj("11222333000182")).toBe(false);
  });

  it("recusa repetição e comprimento errado", () => {
    expect(isValidCpf("11111111111")).toBe(false);
    expect(isValidCnpj("11111111111111")).toBe(false);
    expect(isValidCpf("123")).toBe(false);
    expect(isValidCnpj("123")).toBe(false);
  });
});
