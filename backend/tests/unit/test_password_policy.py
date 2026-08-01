import pytest

from app.core.security import validate_password_policy


@pytest.mark.parametrize(
    ("password", "expected_error_count"),
    [
        ("Abc123!x", 0),
        ("abc123!x", 1),  # falta maiúscula
        ("ABC123!X", 1),  # falta minúscula
        ("Abcdefg!", 1),  # falta número
        ("Abc12345", 1),  # falta especial
        ("Ab1!", 1),  # só falha por ser curto — os outros 4 critérios estão ok
        ("", 5),  # tudo falha
    ],
)
def test_password_policy_cases(password: str, expected_error_count: int) -> None:
    errors = validate_password_policy(password)
    assert len(errors) == expected_error_count


def test_valid_password_has_no_errors() -> None:
    assert validate_password_policy("Abc123!x") == []


def test_short_password_is_flagged() -> None:
    errors = validate_password_policy("A1!")
    assert "Mínimo de 8 caracteres." in errors
