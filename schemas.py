from pydantic import BaseModel
from typing import Optional, List

class BulkDeleteRequest(BaseModel):
    ids: List[int]

class SpecialistBase(BaseModel):
    name: str
    phone_number: str
    role: str

class SpecialistCreate(SpecialistBase):
    pass

class SpecialistResponse(SpecialistBase):
    id: int
    class Config:
        from_attributes = True


class SupportRequestBase(BaseModel):
    first_name: str
    last_name: str
    office_number: str
    institute_branch: str
    requester_email: str
    requester_phone: str
    message: str
    priority: str

class SupportRequestCreate(SupportRequestBase):
    pass

class SupportRequestResponse(SupportRequestBase):
    id: int
    status: str
    assigned_specialist_id: Optional[int] = None
    created_at: Optional[int] = None
    assigned_at: Optional[int] = None
    resolved_at: Optional[int] = None
    
    class Config:
        from_attributes = True


class AssignRequest(BaseModel):
    specialist_id: int


class SmsAuditLogResponse(BaseModel):
    id: int
    ticket_id: Optional[int] = None
    recipient: str
    timestamp: int
    provider_response_code: Optional[str] = None
    cost: Optional[float] = None

    http_status: Optional[int] = None
    provider_message: Optional[str] = None

    class Config:
        from_attributes = True


class SystemAlertResponse(BaseModel):
    id: int
    alert_type: str
    message: str
    created_at: int
    resolved_at: Optional[int] = None

    class Config:
        from_attributes = True
