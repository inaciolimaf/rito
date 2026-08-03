"""Validação pura de anexos (spec 035, regra 5) — sem banco, sem storage.

A política é allowlist de MIME + blocklist de extensões executáveis: o tipo precisa
estar na lista permitida E a extensão não pode ser de executável (um ".exe" renomeado
para content-type inocente continua bloqueado).
"""

MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024  # 50 MB (regra 5)

ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "text/plain",
        "text/csv",
        "application/json",
        "application/zip",
        "application/x-zip-compressed",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
    }
)

EXECUTABLE_EXTENSIONS = frozenset(
    {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".msi",
        ".scr",
        ".ps1",
        ".sh",
        ".bash",
        ".vbs",
        ".js",
        ".jar",
        ".apk",
        ".dll",
    }
)

EXECUTABLE_CONTENT_TYPES = frozenset(
    {
        "application/x-msdownload",
        "application/x-msdos-program",
        "application/x-executable",
        "application/x-sh",
        "application/java-archive",
    }
)


class AttachmentTooLargeError(Exception):
    """Regra 5: acima de 50 MB → 422."""


class AttachmentTypeBlockedError(Exception):
    """Regra 5: tipo fora da allowlist ou executável → 422."""


def validate_attachment(*, filename: str, content_type: str, size_bytes: int) -> None:
    if size_bytes > MAX_ATTACHMENT_BYTES:
        raise AttachmentTooLargeError
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if (
        extension in EXECUTABLE_EXTENSIONS
        or content_type in EXECUTABLE_CONTENT_TYPES
        or content_type not in ALLOWED_CONTENT_TYPES
    ):
        raise AttachmentTypeBlockedError
