from app.core.rls import enable_rls_statements


def test_enable_rls_statements_generates_expected_sql() -> None:
    statements = enable_rls_statements("processos")

    assert 'ALTER TABLE "processos" ENABLE ROW LEVEL SECURITY' in statements
    assert 'ALTER TABLE "processos" FORCE ROW LEVEL SECURITY' in statements
    assert any('CREATE POLICY tenant_isolation ON "processos"' in s for s in statements)
    assert any("current_setting('app.tenant_id', true)::uuid" in s for s in statements)
    assert any("CREATE INDEX ix_processos_tenant" in s for s in statements)
