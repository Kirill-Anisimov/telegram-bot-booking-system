# models.py
import enum

from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from database import Base


class RoomType(enum.Enum):
    DRUMS = "drums"
    BASS = "bass"
    VOCAL = "vocal"
    GUITAR = "guitar"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    full_name = Column(String)


class Slot(Base):
    __tablename__ = "slots"

    id = Column(Integer, primary_key=True)
    date = Column(Date)
    time = Column(String)
    room = Column(Enum(RoomType), nullable=False)
    is_booked = Column(Boolean, default=False)
    booked_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    booked_by = relationship("User")
