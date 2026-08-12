class DunningRuleConflictError(Exception):
    """Já existe uma régua com o mesmo (days_offset, channel) — UNIQUE da migration."""


class TransactionNotEligibleError(Exception):
    """Lançamento não é RECEITA em aberto (não faz sentido cobrar) — regra implícita
    do envio manual (regra 8): "sempre permitido" pressupõe que ainda há o que cobrar."""


class CustomerRequiredError(Exception):
    """Lançamento sem `customer_id` — não há para quem enviar a cobrança."""
