import datetime as dt
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

def get_current_time():
    return dt.datetime.now(dt.timezone.utc)

class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String, nullable=False)
    datetime = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, completed, cancelled
    created_at = Column(DateTime, default=get_current_time)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "datetime": self.datetime,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String, nullable=False)
    priority = Column(String, default="medium")  # low, medium, high
    due_date = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, in_progress, completed
    created_at = Column(DateTime, default=get_current_time)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "due_date": self.due_date,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

