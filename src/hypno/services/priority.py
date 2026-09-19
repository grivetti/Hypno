from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime

from ..models import Person, PersonRelationship


@dataclass(frozen=True)
class PriorityWeights:
    contact: float = 0.50
    bond_gap: float = 0.20
    monthly_activity: float = 0.15
    birthday: float = 0.15

    def __post_init__(self) -> None:
        total = (
            self.contact
            + self.bond_gap
            + self.monthly_activity
            + self.birthday
        )

        if abs(total - 1.0) > 0.0001:
            raise ValueError(
                f"Os pesos devem somar 1.0. Valor atual: {total}"
            )


@dataclass(frozen=True)
class PriorityResult:
    person_id: int
    person_name: str

    score: float
    percentage: int

    days_since_last_interaction: int | None
    interactions_this_month: int
    days_until_birthday: int | None

    target_contact_days: int | None

    contact_score: float
    bond_gap_score: float
    monthly_activity_score: float
    birthday_score: float

    current_bond_level: int | None
    desired_bond_level: int | None

    reasons: tuple[str, ...]


def clamp(
    value: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    return max(minimum, min(value, maximum))


def get_target_contact_days(
    relationships: list[PersonRelationship],
) -> int | None:
    """
    Uma pessoa pode possuir vários tipos de relacionamento.

    Exemplo:
        friend -> 14 dias
        coworker -> 30 dias

    Nesse caso usamos o intervalo mais exigente: 14 dias.
    """

    intervals = [
        relationship.max_days_without_contact
        for relationship in relationships
        if relationship.max_days_without_contact is not None
    ]

    if not intervals:
        return None

    return min(intervals)


def get_last_interaction_at(person: Person) -> datetime | None:
    if not person.interactions:
        return None

    return max(
        interaction.occurred_at
        for interaction in person.interactions
    )


def get_days_since_last_interaction(
    person: Person,
    today: date,
) -> int | None:
    last_interaction = get_last_interaction_at(person)

    if last_interaction is None:
        return None

    return (today - last_interaction.date()).days


def count_interactions_this_month(
    person: Person,
    today: date,
) -> int:
    return sum(
        1
        for interaction in person.interactions
        if (
            interaction.occurred_at.year == today.year
            and interaction.occurred_at.month == today.month
        )
    )


def calculate_contact_score(
    *,
    person: Person,
    today: date,
    target_days: int | None,
) -> float:
    """
    Calcula a urgência baseada no intervalo desejado.

    Exemplos para target_days=30:

        15 dias -> ~0.40
        30 dias -> 0.80
        45 dias -> 0.90
        60 dias -> 1.00

    Quando nunca houve interação, usa created_at como referência.
    """

    if target_days is None:
        return 0.0

    if target_days <= 0:
        return 0.0

    last_interaction = get_last_interaction_at(person)

    if last_interaction is not None:
        days = (today - last_interaction.date()).days
    else:
        days = (today - person.created_at.date()).days

    days = max(days, 0)

    ratio = days / target_days

    # Até atingir max_days_without_contact:
    # cresce de 0 até 0.8.
    if ratio <= 1:
        return clamp(ratio * 0.8)

    # Depois do limite, cresce mais lentamente.
    # Em 2x o intervalo chega a 1.
    return clamp(
        0.8 + ((ratio - 1) * 0.2)
    )


def calculate_bond_gap_score(
    relationships: list[PersonRelationship],
) -> float:
    """
    Retorna o maior gap entre vínculo atual e desejado.

    bond_level: 0..10
    desired_bond_level: 0..10
    """

    gaps: list[int] = []

    for relationship in relationships:
        if (
            relationship.bond_level is None
            or relationship.desired_bond_level is None
        ):
            continue

        gap = (
            relationship.desired_bond_level
            - relationship.bond_level
        )

        gaps.append(max(gap, 0))

    if not gaps:
        return 0.0

    return clamp(max(gaps) / 10)


def get_main_bond_levels(
    relationships: list[PersonRelationship],
) -> tuple[int | None, int | None]:
    """
    Retorna o relacionamento com maior gap positivo.

    Isso é usado principalmente para exibir no CLI/email.
    """

    candidates = [
        relationship
        for relationship in relationships
        if (
            relationship.bond_level is not None
            and relationship.desired_bond_level is not None
        )
    ]

    if not candidates:
        return None, None

    selected = max(
        candidates,
        key=lambda relationship: (
            relationship.desired_bond_level
            - relationship.bond_level
        ),
    )

    return (
        selected.bond_level,
        selected.desired_bond_level,
    )


def calculate_monthly_activity_score(
    *,
    interactions_this_month: int,
    target_days: int | None,
    today: date,
) -> float:
    """
    Compara quantidade de interações do mês com a frequência esperada.

    A frequência esperada é derivada de max_days_without_contact.

    14 dias -> aproximadamente 2 interações/mês
    30 dias -> aproximadamente 1 interação/mês
    90 dias -> aproximadamente 0.33 interação/mês
    """

    if target_days is None or target_days <= 0:
        return 0.0

    days_in_month = monthrange(
        today.year,
        today.month,
    )[1]

    expected = days_in_month / target_days

    deficit = max(
        expected - interactions_this_month,
        0.0,
    )

    # max(1, expected) evita que uma frequência de
    # 90 dias gere score 1 só porque houve zero
    # interações no mês.
    return clamp(
        deficit / max(expected, 1.0)
    )


def get_next_birthday(
    birthday: date | None,
    today: date,
) -> date | None:
    if birthday is None:
        return None

    def birthday_for_year(year: int) -> date:
        try:
            return date(
                year,
                birthday.month,
                birthday.day,
            )
        except ValueError:
            # 29 de fevereiro em ano não bissexto.
            return date(year, 2, 28)

    next_birthday = birthday_for_year(today.year)

    if next_birthday < today:
        next_birthday = birthday_for_year(
            today.year + 1
        )

    return next_birthday


def get_days_until_birthday(
    birthday: date | None,
    today: date,
) -> int | None:
    next_birthday = get_next_birthday(
        birthday,
        today,
    )

    if next_birthday is None:
        return None

    return (next_birthday - today).days


def calculate_birthday_score(
    days_until_birthday: int | None,
    *,
    window_days: int = 30,
) -> float:
    if days_until_birthday is None:
        return 0.0

    if days_until_birthday < 0:
        return 0.0

    if days_until_birthday > window_days:
        return 0.0

    return clamp(
        1 - (days_until_birthday / window_days)
    )


def build_reasons(
    *,
    person: Person,
    target_days: int | None,
    days_since_last_interaction: int | None,
    interactions_this_month: int,
    days_until_birthday: int | None,
    current_bond: int | None,
    desired_bond: int | None,
) -> tuple[str, ...]:
    reasons: list[str] = []

    if days_since_last_interaction is None:
        reasons.append(
            "Nenhuma interação registrada."
        )

    elif (
        target_days is not None
        and days_since_last_interaction >= target_days
    ):
        overdue = (
            days_since_last_interaction
            - target_days
        )

        if overdue == 0:
            reasons.append(
                f"Chegou ao limite de {target_days} dias sem contato."
            )
        else:
            reasons.append(
                f"Contato atrasado em {overdue} dias "
                f"(limite: {target_days})."
            )

    elif days_since_last_interaction is not None:
        reasons.append(
            f"Última interação há "
            f"{days_since_last_interaction} dias."
        )

    if interactions_this_month == 0:
        reasons.append(
            "Nenhuma interação neste mês."
        )
    elif interactions_this_month == 1:
        reasons.append(
            "1 interação neste mês."
        )
    else:
        reasons.append(
            f"{interactions_this_month} interações neste mês."
        )

    if (
        current_bond is not None
        and desired_bond is not None
        and desired_bond > current_bond
    ):
        reasons.append(
            f"Vínculo desejado é maior que o atual "
            f"({current_bond} → {desired_bond})."
        )

    if days_until_birthday is not None:
        if days_until_birthday == 0:
            reasons.append(
                "Aniversário é hoje."
            )
        elif days_until_birthday <= 30:
            reasons.append(
                f"Aniversário em "
                f"{days_until_birthday} dias."
            )

    return tuple(reasons)


def calculate_person_priority(
    person: Person,
    *,
    today: date | None = None,
    weights: PriorityWeights | None = None,
) -> PriorityResult:
    today = today or date.today()
    weights = weights or PriorityWeights()

    target_days = get_target_contact_days(
        person.relationships
    )

    days_since = get_days_since_last_interaction(
        person,
        today,
    )

    interactions_this_month = (
        count_interactions_this_month(
            person,
            today,
        )
    )

    days_until_birthday = (
        get_days_until_birthday(
            person.birthday,
            today,
        )
    )

    contact = calculate_contact_score(
        person=person,
        today=today,
        target_days=target_days,
    )

    bond_gap = calculate_bond_gap_score(
        person.relationships
    )

    monthly_activity = (
        calculate_monthly_activity_score(
            interactions_this_month=interactions_this_month,
            target_days=target_days,
            today=today,
        )
    )

    birthday = calculate_birthday_score(
        days_until_birthday
    )

    score = (
        contact * weights.contact
        + bond_gap * weights.bond_gap
        + monthly_activity * weights.monthly_activity
        + birthday * weights.birthday
    )

    score = round(clamp(score), 4)

    current_bond, desired_bond = (
        get_main_bond_levels(
            person.relationships
        )
    )

    reasons = build_reasons(
        person=person,
        target_days=target_days,
        days_since_last_interaction=days_since,
        interactions_this_month=interactions_this_month,
        days_until_birthday=days_until_birthday,
        current_bond=current_bond,
        desired_bond=desired_bond,
    )

    return PriorityResult(
        person_id=person.id,
        person_name=person.name,
        score=score,
        percentage=round(score * 100),
        days_since_last_interaction=days_since,
        interactions_this_month=interactions_this_month,
        days_until_birthday=days_until_birthday,
        target_contact_days=target_days,
        contact_score=round(contact, 4),
        bond_gap_score=round(bond_gap, 4),
        monthly_activity_score=round(
            monthly_activity,
            4,
        ),
        birthday_score=round(birthday, 4),
        current_bond_level=current_bond,
        desired_bond_level=desired_bond,
        reasons=reasons,
    )