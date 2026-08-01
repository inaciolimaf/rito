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
