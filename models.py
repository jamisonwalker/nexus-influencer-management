from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from typing import List, Optional

Base = declarative_base()

class FanLore(Base):
    """
    Represents fan-specific information and lore.
    
    This model stores personal information about fans, including their name,
    fan-specific lore text, last known vibe, and blocked status.
    """
    
    __tablename__ = "fan_lore"
    
    fan_id = Column(String, primary_key=True, index=True) 
    name = Column(String, nullable=False)
    lore_text = Column(Text)                
    last_vibe = Column(String)              
    created_at = Column(DateTime, server_default=func.now())
    
    # Note: is_blocked column is NOT in the actual database schema
    # This field is commented out to match the real database
    
    # Relationship to history
    messages = relationship(
        "Message", 
        back_populates="fan", 
        order_by="Message.created_at",
        lazy="select"
    )
    
    def __repr__(self):
        return f"<FanLore(fan_id={self.fan_id}, name={self.name})>"

class Message(Base):
    """
    Represents a chat message between a fan and Sarah.
    
    This model stores individual messages with their role (user or assistant),
    content, and timestamp.
    """
    
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, index=True)  # Message UUID from Fanvue
    fan_id = Column(String, ForeignKey("fan_lore.fan_id"), index=True)
    topic = Column(Text)
    role = Column(String, nullable=False)              # "user" or "assistant"
    extension = Column(Text)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    payload = Column(JSON)
    event = Column(Text)
    private = Column(Boolean, default=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    inserted_at = Column(DateTime, server_default=func.now())
    
    fan = relationship("FanLore", back_populates="messages")
    
    def __repr__(self):
        return f"<Message(id={self.id}, fan_id={self.fan_id}, role={self.role})>"
