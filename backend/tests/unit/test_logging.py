import io
import json
import logging

from app.core.logging import JSONFormatter, request_id_var


def test_request_id_propagates_to_log_output() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())

    logger = logging.getLogger("test.request-id")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    token = request_id_var.set("abc-123")
    try:
        logger.info("mensagem de teste")
    finally:
        request_id_var.reset(token)

    payload = json.loads(stream.getvalue())
    assert payload["request_id"] == "abc-123"
    assert payload["message"] == "mensagem de teste"


def test_exception_info_is_formatted_into_payload() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())

    logger = logging.getLogger("test.exception")
    logger.handlers = [handler]
    logger.setLevel(logging.ERROR)
    logger.propagate = False

    try:
        raise ValueError("algo quebrou")
    except ValueError:
        logger.exception("erro não tratado")

    payload = json.loads(stream.getvalue())
    assert "ValueError: algo quebrou" in payload["exception"]
