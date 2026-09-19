from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .base import Base
from .utils import *

DATABASE_PATH = f"{CONFIG_DIR}/life.db"


engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    echo=False,
)


@event.listens_for(
    engine,
    "connect",
)
def enable_foreign_keys(
    dbapi_connection,
    connection_record,
):
    cursor = dbapi_connection.cursor()

    cursor.execute(
        "PRAGMA foreign_keys=ON"
    )

    cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


def get_session() -> Session:
    return SessionLocal()


# ------------------------------------------------------------
# IMPORTANTE:
# importa os models ANTES de executar create_all()
# ------------------------------------------------------------

from . import models  # noqa: E402, F401


# ------------------------------------------------------------
# Executado imediatamente quando hypno.database é importado.
# Isso abre/cria o SQLite e cria todas as tabelas conhecidas.
# ------------------------------------------------------------

Base.metadata.create_all(
    bind=engine
)