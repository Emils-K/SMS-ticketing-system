from sqlalchemy import Column, Integer, String, ForeignKey, Float
from sqlalchemy.orm import relationship
from database import Base

class Specialist(Base):
    __tablename__ = "specialists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    phone_number = Column(String)
    phone_last4 = Column(String, nullable=True)
    role = Column(String, default="IT Specialist")

    requests = relationship("SupportRequest", back_populates="assigned_specialist")


class SupportRequest(Base):
    __tablename__ = "support_requests"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    office_number = Column(String)
    institute_branch = Column(String)
    requester_email = Column(String)
    requester_phone = Column(String)
    requester_phone_last4 = Column(String, nullable=True)
    message = Column(String)
    priority = Column(String)
    status = Column(String, default="Pending") # Pending, Assigned, Resolved
    created_at = Column(Integer, nullable=True)
    assigned_at = Column(Integer, nullable=True)
    resolved_at = Column(Integer, nullable=True)
    
    assigned_specialist_id = Column(Integer, ForeignKey("specialists.id"), nullable=True)
    assigned_specialist = relationship("Specialist", back_populates="requests")


class SmsAuditLog(Base):
    __tablename__ = "sms_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_requests.id"), nullable=True, index=True)
    recipient = Column(String)  # masked phone, e.g. ****4496
    timestamp = Column(Integer, index=True)  # unix seconds
    provider_response_code = Column(String, nullable=True)
    cost = Column(Float, nullable=True)

    http_status = Column(Integer, nullable=True)
    provider_message = Column(String, nullable=True)


class SystemAlert(Base):
    __tablename__ = "system_alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String, index=True)  # e.g. LOW_BALANCE
    message = Column(String)
    created_at = Column(Integer, index=True)
    resolved_at = Column(Integer, nullable=True)
