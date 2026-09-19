from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Person, PersonInterest
from .priority import PriorityResult
from .recommendations import get_recommendations


@dataclass(frozen=True)
class DigestEntry:
    priority: PriorityResult
    interests: tuple[str, ...]
    suggestion: str


@dataclass(frozen=True)
class DailyDigest:
    date: date

    priorities: tuple[DigestEntry, ...]
    birthdays: tuple[DigestEntry, ...]

    total_people: int
    interactions_this_month: int


def _get_people(
    session: Session,
    person_ids: set[int],
) -> dict[int, Person]:
    if not person_ids:
        return {}

    statement = (
        select(Person)
        .where(Person.id.in_(person_ids))
        .options(
            selectinload(Person.interests)
            .selectinload(PersonInterest.interest)
        )
    )

    people = session.scalars(
        statement
    ).all()

    return {
        person.id: person
        for person in people
    }


def _get_interests(
    person: Person | None,
) -> tuple[str, ...]:
    if person is None:
        return ()

    interests = [
        person_interest.interest.name
        for person_interest in person.interests
        if person_interest.sentiment == "like"
    ]

    return tuple(
        sorted(interests)
    )


def _build_suggestion(
    result: PriorityResult,
    interests: tuple[str, ...],
) -> str:
    interest = (
        interests[0]
        if interests
        else None
    )

    if result.days_until_birthday == 0:
        return (
            "Envie uma mensagem de aniversário hoje."
        )

    if (
        result.days_until_birthday is not None
        and result.days_until_birthday <= 7
    ):
        return (
            "O aniversário está próximo. "
            "Considere preparar uma mensagem ou convite."
        )

    overdue = (
        result.target_contact_days is not None
        and result.days_since_last_interaction is not None
        and result.days_since_last_interaction
        >= result.target_contact_days
    )

    if overdue:
        if interest:
            return (
                "Retome o contato. "
                f"Você pode puxar assunto sobre {interest}."
            )

        return (
            "Retome o contato com uma mensagem simples "
            "perguntando como a pessoa está."
        )

    bond_growth = (
        result.current_bond_level is not None
        and result.desired_bond_level is not None
        and result.desired_bond_level
        > result.current_bond_level
    )

    if bond_growth:
        if interest:
            return (
                "Como você deseja fortalecer esse vínculo, "
                f"considere iniciar uma conversa sobre {interest}."
            )

        return (
            "Considere iniciar uma conversa um pouco mais "
            "pessoal para fortalecer o vínculo."
        )

    if interest:
        return (
            f"Uma mensagem breve relacionada a {interest} "
            "pode ser uma forma natural de manter contato."
        )

    return (
        "Uma mensagem curta para saber como a pessoa está "
        "pode ser suficiente."
    )


def _make_entry(
    result: PriorityResult,
    people: dict[int, Person],
) -> DigestEntry:
    person = people.get(
        result.person_id
    )

    interests = _get_interests(
        person
    )

    return DigestEntry(
        priority=result,
        interests=interests,
        suggestion=_build_suggestion(
            result,
            interests,
        ),
    )


def build_daily_digest(
    session: Session,
    *,
    today: date | None = None,
    limit: int = 10,
    minimum_priority: float = 0.25,
    birthday_window: int = 30,
) -> DailyDigest:
    today = today or date.today()

    all_results = get_recommendations(
        session,
        limit=None,
        today=today,
    )

    priority_results = [
        result
        for result in all_results
        if result.score >= minimum_priority
    ][:limit]

    birthday_results = [
        result
        for result in all_results
        if (
            result.days_until_birthday is not None
            and result.days_until_birthday
            <= birthday_window
        )
    ]

    birthday_results.sort(
        key=lambda result:
        result.days_until_birthday
        if result.days_until_birthday is not None
        else 9999
    )

    person_ids = {
        result.person_id
        for result in (
            priority_results
            + birthday_results
        )
    }

    people = _get_people(
        session,
        person_ids,
    )

    priority_entries = tuple(
        _make_entry(
            result,
            people,
        )
        for result in priority_results
    )

    birthday_entries = tuple(
        _make_entry(
            result,
            people,
        )
        for result in birthday_results
    )

    total_interactions = sum(
        result.interactions_this_month
        for result in all_results
    )

    return DailyDigest(
        date=today,
        priorities=priority_entries,
        birthdays=birthday_entries,
        total_people=len(all_results),
        interactions_this_month=total_interactions,
    )

def _format_last_interaction(
    result: PriorityResult,
) -> str:
    days = result.days_since_last_interaction

    if days is None:
        return "Nenhuma interação registrada"

    if days == 0:
        return "Última interação: hoje"

    if days == 1:
        return "Última interação: há 1 dia"

    return (
        f"Última interação: há {days} dias"
    )


def _format_bond(
    result: PriorityResult,
) -> str | None:
    current = result.current_bond_level
    desired = result.desired_bond_level

    if current is None or desired is None:
        return None

    return (
        f"Vínculo atual/desejado: "
        f"{current} → {desired}"
    )


def render_digest_text(
    digest: DailyDigest,
) -> str:
    lines: list[str] = []

    lines.append(
        f"Hypno — Digest Social — "
        f"{digest.date.strftime('%d/%m/%Y')}"
    )

    lines.append("")
    lines.append("RESUMO")
    lines.append("------")

    lines.append(
        f"Pessoas cadastradas: "
        f"{digest.total_people}"
    )

    lines.append(
        f"Interações neste mês: "
        f"{digest.interactions_this_month}"
    )

    lines.append("")
    lines.append("PRIORIDADES")
    lines.append("-----------")

    if not digest.priorities:
        lines.append(
            "Nenhuma interação urgente hoje."
        )

    for index, entry in enumerate(
        digest.priorities,
        start=1,
    ):
        result = entry.priority

        lines.append("")
        lines.append(
            f"{index}. "
            f"{result.person_name} "
            f"— {result.percentage}%"
        )

        lines.append(
            _format_last_interaction(
                result
            )
        )

        lines.append(
            f"Interações neste mês: "
            f"{result.interactions_this_month}"
        )

        if (
            result.target_contact_days
            is not None
        ):
            lines.append(
                "Frequência desejada: "
                f"{result.target_contact_days} dias"
            )

        bond = _format_bond(result)

        if bond:
            lines.append(bond)

        if entry.interests:
            lines.append(
                "Interesses: "
                + ", ".join(
                    entry.interests
                )
            )

        lines.append(
            f"Sugestão: {entry.suggestion}"
        )

        if result.reasons:
            lines.append("Motivos:")

            for reason in result.reasons:
                lines.append(
                    f"  - {reason}"
                )

    lines.append("")
    lines.append("ANIVERSÁRIOS")
    lines.append("------------")

    if not digest.birthdays:
        lines.append(
            "Nenhum aniversário nos próximos 30 dias."
        )

    for entry in digest.birthdays:
        result = entry.priority

        days = result.days_until_birthday

        if days == 0:
            when = "hoje"
        elif days == 1:
            when = "amanhã"
        else:
            when = f"em {days} dias"

        lines.append(
            f"- {result.person_name}: {when}"
        )

    return "\n".join(lines)
  
def render_digest_html(
      digest: DailyDigest,
  ) -> str:
      priority_html: list[str] = []

      for entry in digest.priorities:
          result = entry.priority

          details = [
              _format_last_interaction(
                  result
              ),
              (
                  "Interações neste mês: "
                  f"{result.interactions_this_month}"
              ),
          ]

          if (
              result.target_contact_days
              is not None
          ):
              details.append(
                  "Frequência desejada: "
                  f"{result.target_contact_days} dias"
              )

          bond = _format_bond(result)

          if bond:
              details.append(bond)

          if entry.interests:
              details.append(
                  "Interesses: "
                  + ", ".join(
                      entry.interests
                  )
              )

          detail_html = "".join(
              f"<li>{escape(detail)}</li>"
              for detail in details
          )

          reasons_html = "".join(
              f"<li>{escape(reason)}</li>"
              for reason in result.reasons
          )

          priority_html.append(
              f"""
              <div style="
                  margin-bottom: 24px;
                  padding-bottom: 16px;
                  border-bottom: 1px solid #ddd;
              ">
                  <h3>
                      {escape(result.person_name)}
                      — {result.percentage}%
                  </h3>

                  <ul>
                      {detail_html}
                  </ul>

                  <p>
                      <strong>Sugestão:</strong>
                      {escape(entry.suggestion)}
                  </p>

                  <p><strong>Motivos:</strong></p>

                  <ul>
                      {reasons_html}
                  </ul>
              </div>
              """
          )

      if not priority_html:
          priority_html.append(
              "<p>Nenhuma interação urgente hoje.</p>"
          )

      birthday_html: list[str] = []

      for entry in digest.birthdays:
          result = entry.priority
          days = result.days_until_birthday

          if days == 0:
              when = "hoje"
          elif days == 1:
              when = "amanhã"
          else:
              when = f"em {days} dias"

          birthday_html.append(
              "<li>"
              f"{escape(result.person_name)}: "
              f"{escape(when)}"
              "</li>"
          )

      if not birthday_html:
          birthday_html.append(
              "<li>"
              "Nenhum aniversário nos próximos 30 dias."
              "</li>"
          )

      date_string = digest.date.strftime(
          "%d/%m/%Y"
      )

      return f"""
      <html>
          <body
              style="
                  font-family:
                      Arial,
                      Helvetica,
                      sans-serif;
                  max-width: 700px;
                  margin: auto;
                  line-height: 1.5;
              "
          >
              <h1>Hypno — Digest Social</h1>

              <p>{escape(date_string)}</p>

              <h2>Resumo</h2>

              <p>
                  Pessoas cadastradas:
                  <strong>
                      {digest.total_people}
                  </strong>
                  <br>

                  Interações neste mês:
                  <strong>
                      {digest.interactions_this_month}
                  </strong>
              </p>

              <h2>Prioridades</h2>

              {''.join(priority_html)}

              <h2>Aniversários</h2>

              <ul>
                  {''.join(birthday_html)}
              </ul>
          </body>
      </html>
      """