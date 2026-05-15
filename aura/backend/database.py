import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./akansha.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, default="default")
    role = Column(String, index=True) # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    pinned = Column(Boolean, default=False, index=True)
    display_order = Column(Float, nullable=True, index=True)
    branch_from_id = Column(Integer, nullable=True, index=True)

class Memory(Base):
    __tablename__ = "memories"
    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String, index=True)
    insight = Column(Text)
    importance = Column(Integer, default=1)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(Text, nullable=True)
    is_completed = Column(Boolean, default=False)
    due_date = Column(DateTime, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class InboxMessage(Base):
    __tablename__ = "inbox_messages"
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String) # 'telegram', 'twitter', 'email'
    sender = Column(String)
    content = Column(Text)
    intent = Column(String, nullable=True)
    sentiment = Column(String, nullable=True)
    is_read = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class UserProfile(Base):
    __tablename__ = "user_profiles"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, default="Arjun Mehta")
    email = Column(String, default="arjun.mehta@devcraft.io")
    bio = Column(Text, default="B.Tech student and AI enthusiast. Building the future with Akansha.")
    preferred_mode = Column(String, default="hybrid")
    voice_gender = Column(String, default="female")
    voice_tone = Column(String, default="friendly")
    voice_language = Column(String, default="telugu_english")
    avatar_style = Column(String, default="companion")
    background_listening = Column(Boolean, default=False)
    interrupt_enabled = Column(Boolean, default=True)
    google_connected = Column(Boolean, default=False)
    google_email = Column(String, nullable=True)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class IntegrationConnection(Base):
    __tablename__ = "integration_connections"
    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, index=True, unique=True)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    scope = Column(Text, nullable=True)
    account_email = Column(String, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
    metadata_json = Column(Text, nullable=True)
    is_connected = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class SpeakerProfile(Base):
    __tablename__ = "speaker_profiles"
    id = Column(Integer, primary_key=True, index=True)
    display_name = Column(String, index=True)
    relationship_to_owner = Column(String, nullable=True)
    access_level = Column(String, default="guest")  # owner | trusted | guest
    notes = Column(Text, nullable=True)
    last_intro_text = Column(Text, nullable=True)
    last_heard_text = Column(Text, nullable=True)
    voice_signature_json = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)


def ensure_profile_columns():
    with engine.begin() as connection:
        try:
            column_rows = connection.execute(text("PRAGMA table_info(user_profiles)")).fetchall()
        except Exception:
            return

        existing_columns = {row[1] for row in column_rows}
        if "voice_language" not in existing_columns:
            connection.execute(text("ALTER TABLE user_profiles ADD COLUMN voice_language VARCHAR DEFAULT 'telugu_english'"))
        if "username" not in existing_columns:
            connection.execute(text("ALTER TABLE user_profiles ADD COLUMN username VARCHAR"))
        if "password" not in existing_columns:
            connection.execute(text("ALTER TABLE user_profiles ADD COLUMN password VARCHAR"))
        if "bio" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE user_profiles ADD COLUMN bio TEXT DEFAULT 'B.Tech student and AI enthusiast. Building the future with Akansha.'"
                )
            )


ensure_profile_columns()


def ensure_speaker_columns():
    with engine.begin() as connection:
        try:
            column_rows = connection.execute(text("PRAGMA table_info(speaker_profiles)")).fetchall()
        except Exception:
            return

        existing_columns = {row[1] for row in column_rows}
        if "last_heard_text" not in existing_columns:
            connection.execute(text("ALTER TABLE speaker_profiles ADD COLUMN last_heard_text TEXT"))
        if "voice_signature_json" not in existing_columns:
            connection.execute(text("ALTER TABLE speaker_profiles ADD COLUMN voice_signature_json TEXT"))


ensure_speaker_columns()


def ensure_chat_message_columns():
    with engine.begin() as connection:
        try:
            column_rows = connection.execute(text("PRAGMA table_info(chat_messages)")).fetchall()
        except Exception:
            return

        existing_columns = {row[1] for row in column_rows}
        if "pinned" not in existing_columns:
            connection.execute(text("ALTER TABLE chat_messages ADD COLUMN pinned BOOLEAN DEFAULT 0"))
        if "display_order" not in existing_columns:
            connection.execute(text("ALTER TABLE chat_messages ADD COLUMN display_order FLOAT"))
            connection.execute(text("UPDATE chat_messages SET display_order = id WHERE display_order IS NULL"))
        if "branch_from_id" not in existing_columns:
            connection.execute(text("ALTER TABLE chat_messages ADD COLUMN branch_from_id INTEGER"))


ensure_chat_message_columns()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
