from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Specialist(Base):
    __tablename__ = "specialists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    phone_number = Column(String)
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
    message = Column(String)
    priority = Column(String)
    status = Column(String, default="Pending") # Pending, Assigned, Resolved
    
    assigned_specialist_id = Column(Integer, ForeignKey("specialists.id"), nullable=True)
    assigned_specialist = relationship("Specialist", back_populates="requests")
