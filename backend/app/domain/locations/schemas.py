from pydantic import BaseModel


class StateResponse(BaseModel):
    code: str
    name: str
    ibge_code: int


class CityResponse(BaseModel):
    ibge_code: int
    name: str
    state_code: str
