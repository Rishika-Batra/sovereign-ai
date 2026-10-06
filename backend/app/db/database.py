import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/sovereign_ai")

engine = create_engine(DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
