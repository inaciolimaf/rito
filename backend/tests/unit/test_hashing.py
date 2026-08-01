from app.core.config import Settings
from app.core.security import hash_password, verify_password


def test_hash_password_verifies_correct_password() -> None:
    password_hash = hash_password("SenhaForte123!")
    assert verify_password("SenhaForte123!", password_hash) is True


def test_hash_password_rejects_wrong_password() -> None:
    password_hash = hash_password("SenhaForte123!")
    assert verify_password("outra-senha", password_hash) is False


def test_production_argon2_parameters_are_not_the_reduced_test_values() -> None:
    """Os parâmetros reais de produção (Settings, sem override de teste) são fortes.

    Os testes acima rodam com ARGON2_TIME_COST/MEMORY_COST reduzidos (conftest.py)
    para não estourar o orçamento de 120s — este teste garante que os valores
    *padrão* da classe Settings (o que roda se nenhuma var de ambiente for setada)
    continuam nos parâmetros recomendados, não nos reduzidos de teste.
    """
    assert Settings.model_fields["argon2_time_cost"].default == 3
    assert Settings.model_fields["argon2_memory_cost"].default == 65536
