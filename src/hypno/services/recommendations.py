from __future__ import annotations

from datetime import date

from ..models import Person

from .priority import (
    PriorityResult,
    calculate_person_priority,
)

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload


def rank_people(
    people: list[Person],
    *,
    today: date | None = None,
) -> list[PriorityResult]:
    results = [
        calculate_person_priority(
            person,
            today=today,
        )
        for person in people
    ]

    return sorted(
        results,
        key=lambda item: item.score,
        reverse=True,
    )


def get_recommendations(
    session: Session,
    *,
    limit: int | None = 10,
    today: date | None = None,
) -> list[PriorityResult]:
    """
    Busca pessoas no banco e retorna o ranking de prioridade.

    A CLI não precisa conhecer detalhes de SQLAlchemy nem
    do algoritmo de prioridade.
    """

    statement = (
        select(Person)
        .options(
            selectinload(Person.interactions),
            selectinload(Person.relationships),
        )
        .order_by(Person.name)
    )

    people = list(
        session.scalars(statement).all()
    )

    results = [
        calculate_person_priority(
            person,
            today=today,
        )
        for person in people
    ]

    results.sort(
        key=lambda result: result.score,
        reverse=True,
    )

    if limit is not None:
        return results[:limit]

    return results