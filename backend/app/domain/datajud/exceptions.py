class CourtNotSupportedError(Exception):
    """Regra 4 (spec 046): tribunal sem `datajud_alias` cadastrado — a API pública
    não tem endpoint para ele, então a consulta nem tenta a rede."""

    def __init__(self, court_code: str) -> None:
        super().__init__(f"Tribunal {court_code} não tem alias DataJud configurado.")
        self.court_code = court_code
