import uuid

from pydantic import BaseModel, EmailStr

from app.domain.users.models import FinancialAccess, UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class MeResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    tenant: uuid.UUID
    role: UserRole
    financial_access: FinancialAccess
    capabilities: list[str]
