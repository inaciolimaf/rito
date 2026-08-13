"""Quota de armazenamento por plano (spec 063, regra 5/6, docs §4.13)."""

from app.domain.account.models import AccountPlan

_BYTES_PER_GB = 1024**3

PLAN_QUOTA_GB: dict[AccountPlan, int] = {
    AccountPlan.ESSENCIAL: 50,
    AccountPlan.BANCA_JURIDICA: 70,
    AccountPlan.BANCA_MAX: 90,
    AccountPlan.ELITE: 100,
}


def quota_bytes(plan: AccountPlan) -> int:
    return PLAN_QUOTA_GB[plan] * _BYTES_PER_GB


class StorageQuotaExceededError(Exception):
    """Regra 5: upload que ultrapassaria a quota do plano é bloqueado antes do IO."""
