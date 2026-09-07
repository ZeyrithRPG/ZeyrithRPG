"""
Conexão com o banco de dados.

Usa a variável de ambiente DATABASE_URL — no Render, isso vai apontar pro Neon
(o banco permanente), não pro disco local do Render (que é apagado a cada reinício).

Pra testar no seu próprio computador antes de subir, funciona com SQLite sem
precisar de nada configurado — só troca a URL depois pra usar o Neon de verdade.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///local_test.db")

# Neon (e Postgres em geral) às vezes manda a URL começando com "postgres://",
# mas o SQLAlchemy moderno exige "postgresql://" — corrige automaticamente.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session():
    return SessionLocal()
