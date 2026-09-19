from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import keyring
from smtplib import SMTPException

import typer
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .database import get_session, SessionLocal
from .models import (
    Interest,
    Interaction,
    Person,
    PersonInterest,
    PersonRelationship,
)


from .notifications.email_sender import (
    send_email,
    test_email_connection
)

from .services.digest import (
    build_daily_digest,
    render_digest_html,
    render_digest_text,
)

from .utils import *



from .services.recommendations import get_recommendations

app = typer.Typer(
    name="Hypno",
    help="Organizador vida pessoal.",
    no_args_is_help=False,
)

# ============================================================
# Application startup
# ============================================================

def run() -> None:
    app()


# ============================================================
# Generic UI helpers
# ============================================================

def title(text: str):
    typer.echo("")
    typer.secho(
        text,
        bold=True,
        fg=typer.colors.CYAN,
    )
    typer.echo("─" * 60)


def pause():
    typer.echo("")
    typer.prompt(
        "Pressionar ENTER para continuar",
        default="",
        show_default=False,
    )


def menu(
    title_text: str,
    options: list[str],
) -> int:
    """
    Mostra um menu e retorna um índice.
    """

    title(title_text)

    for index, option in enumerate(
        options,
        start=1,
    ):
        typer.echo(
            f"  {index}. {option}"
        )

    typer.echo("")

    while True:
        choice = typer.prompt(
            "Choose",
            type=int,
        )

        if 1 <= choice <= len(options):
            return choice - 1

        typer.echo(
            "Escolha inválida."
        )


def confirm(
    message: str,
) -> bool:
    return typer.confirm(
        message,
        default=False,
    )


# ============================================================
# Person lookup
# ============================================================

def find_people(
    session,
    query: str = "",
) -> list[Person]:

    statement = (
        select(Person)
        .order_by(Person.name)
    )

    if query:
        statement = statement.where(
            Person.name.ilike(
                f"%{query}%"
            )
        )

    return session.scalars(
        statement
    ).all()


def load_person(
    session,
    person_id: int,
) -> Person | None:

    return session.scalar(
        select(Person)
        .where(Person.id == person_id)
        .options(
            selectinload(Person.interests)
            .selectinload(
                PersonInterest.interest
            ),

            selectinload(
                Person.relationships
            ),

            selectinload(
                Person.interactions
            ),

            selectinload(
                Person.conversation_topics
            ).selectinload(
                ConversationTopic.interest
            ),
        )
    )

def choose_person(
    session,
    prompt: str = "Procurar Pessoa",
) -> Person | None:

    query = typer.prompt(
        prompt,
        default="",
        show_default=False,
    ).strip()

    people = find_people(
        session,
        query,
    )

    if not people:
        typer.secho(
            "Nínguem encontrado.",
            fg=typer.colors.YELLOW,
        )
        return None

    if len(people) == 1:
        return load_person(
            session,
            people[0].id,
        )

    options = [
        person.name
        for person in people
    ]

    index = menu(
        "Escolha a pessoa",
        options,
    )

    return load_person(
        session,
        people[index].id,
    )


# ============================================================
# Input helpers
# ============================================================

def ask_text(
    label: str,
    default: str | None = None,
) -> str | None:

    if default is None:
        value = typer.prompt(
            label,
            default="",
            show_default=False,
        )
    else:
        value = typer.prompt(
            label,
            default=default,
        )

    value = value.strip()

    return value or None


def ask_date(
    label: str,
    default: date | None = None,
) -> date | None:

    default_text = (
        default.isoformat()
        if default
        else ""
    )

    while True:

        value = typer.prompt(
            label,
            default=default_text,
        ).strip()

        if not value:
            return None

        try:
            return date.fromisoformat(
                value
            )
        except ValueError:
            typer.secho(
                "Please use YYYY-MM-DD.",
                fg=typer.colors.RED,
            )


def ask_int(
    label: str,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:

    while True:

        if default is None:
            value = typer.prompt(
                label,
                default="",
                show_default=False,
            )
        else:
            value = typer.prompt(
                label,
                default=str(default),
            )

        if not value.strip():
            return None

        try:
            result = int(value)
        except ValueError:
            typer.echo(
                "Por favor, entre um número."
            )
            continue

        if minimum is not None:
            if result < minimum:
                typer.echo(
                    f"O mínimo é {minimum}."
                )
                continue

        if maximum is not None:
            if result > maximum:
                typer.echo(
                    f"O Máximo é {maximum}."
                )
                continue

        return result


def ask_list(
    label: str,
    default: list[str] | None = None,
) -> list[str]:

    default_text = ", ".join(
        default or []
    )

    value = typer.prompt(
        label,
        default=default_text,
    )

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]

# ============================================================
# Interests
# ============================================================

def get_interest_names(
    person: Person,
    sentiment: str,
) -> list[str]:

    return [
        item.interest.name
        for item in person.interests
        if item.sentiment == sentiment
    ]


def replace_interests(
    session,
    person: Person,
    likes: list[str],
    neutral: list[str],
    dislikes: list[str],
):

    # Delete existing associations.
    for item in list(person.interests):
        session.delete(item)

    session.flush()

    groups = {
        "like": likes,
        "neutral": neutral,
        "dislike": dislikes,
    }

    for sentiment, names in groups.items():

        for name in names:

            interest = session.scalar(
                select(Interest)
                .where(
                    Interest.name.ilike(name)
                )
            )

            if interest is None:
                interest = Interest(
                    name=name
                )

                session.add(interest)
                session.flush()

            session.add(
                PersonInterest(
                    person_id=person.id,
                    interest_id=interest.id,
                    sentiment=sentiment,
                )
            )


# ============================================================
# CREATE
# ============================================================

@app.command()
def create():
    """
    Adiciona uma pessoa de forma interativa.
    """

    with get_session() as session:

        title("Adicionar Pessoa")

        name = ask_text(
            "Nome"
        )

        if not name:
            typer.echo(
                "Nome é obrigatório."
            )
            raise typer.Exit(1)

        # ----------------------------------------------------
        # Basic information
        # ----------------------------------------------------

        title("Informações Básicas")

        birthday = ask_date(
            "Aniversário [YYYY-MM-DD]"
        )

        cellphone = ask_text(
            "Telefone"
        )

        email = ask_text(
            "Email"
        )

        photo = ask_text(
            "Localização de foto"
        )

        notes = ask_text(
            "Notas"
        )

        # ----------------------------------------------------
        # Relationship
        # ----------------------------------------------------

        title("Relacionamento")

        relationship_type = ask_text(
            "Tipo de relacionamento",
            "amigo",
        )

        bond = ask_int(
            "Vínculo atual [1-5]",
            3,
            1,
            5,
        )

        desired_bond = ask_int(
            "Vínculo desejado [1-5]",
            3,
            1,
            5,
        )

        max_days = ask_int(
            "Máximo de dias sem contato",
            14,
            1,
        )

        # ----------------------------------------------------
        # Interests
        # ----------------------------------------------------

        title("Interesses")

        likes = ask_list(
            "Gosta de [separado por virgula]"
        )

        neutral = ask_list(
            "Neutro em [separado por virgula]"
        )

        dislikes = ask_list(
            "Não gosta de [separado por virgula]"
        )

        # ----------------------------------------------------
        # Confirmation
        # ----------------------------------------------------

        title("Revisão")

        typer.echo(
            f"Nome:       {name}"
        )

        typer.echo(
            f"Aniversário:   "
            f"{birthday or '-'}"
        )

        typer.echo(
            f"Telefone:  "
            f"{cellphone or '-'}"
        )

        typer.echo(
            f"Email:      "
            f"{email or '-'}"
        )

        typer.echo(
            f"Relacionamento: "
            f"{relationship_type}"
        )

        typer.echo(
            f"Vínculo:        "
            f"{bond}/10"
        )

        typer.echo(
            f"Vínculo desejado:     "
            f"{desired_bond}/10"
        )

        typer.echo(
            f"Máximo de dias:    "
            f"{max_days}"
        )

        typer.echo(
            f"Gosta de:       "
            f"{', '.join(likes) or '-'}"
        )

        typer.echo(
            f"Neutro em:     "
            f"{', '.join(neutral) or '-'}"
        )

        typer.echo(
            f"Não gosta de:    "
            f"{', '.join(dislikes) or '-'}"
        )

        typer.echo("")

        if not confirm(
            "Adicionar essa pessoa?"
        ):
            typer.echo(
                "Cancelado."
            )
            return

        # ----------------------------------------------------
        # Save
        # ----------------------------------------------------

        person = Person(
            name=name,
            birthday=birthday,
            cellphone=cellphone,
            email=email,
            photo_path=photo,
            notes=notes,
        )

        session.add(person)
        session.flush()

        relationship = PersonRelationship(
            person_id=person.id,
            relationship_type=relationship_type,
            bond_level=bond,
            desired_bond_level=desired_bond,
            max_days_without_contact=max_days,
        )

        session.add(
            relationship
        )

        replace_interests(
            session,
            person,
            likes,
            neutral,
            dislikes,
        )

        session.commit()

        typer.secho(
            f"\n✓ {name} adicionada.",
            fg=typer.colors.GREEN,
        )


# ============================================================
# SHOW
# ============================================================

@app.command()
def show():
    """
    Encontra e mostra dados de uma pessoa.
    """

    with get_session() as session:

        person = choose_person(
            session
        )

        if person is None:
            return

        display_person(
            person
        )


def display_person(
    person: Person,
):

    today = date.today()

    title(
        person.name
    )

    if person.birthday:

        age = (
            today.year
            - person.birthday.year
        )

        if (
            today.month,
            today.day,
        ) < (
            person.birthday.month,
            person.birthday.day,
        ):
            age -= 1

        typer.echo(
            f"Aniversário:  {person.birthday}"
        )

        typer.echo(
            f"Idade:       {age}"
        )

    else:
        typer.echo(
            "Aniversário:  -"
        )

    typer.echo(
        f"Telefone: "
        f"{person.cellphone or '-'}"
    )

    typer.echo(
        f"Email:     "
        f"{person.email or '-'}"
    )

    typer.echo(
        f"Localização de foto:     "
        f"{person.photo_path or '-'}"
    )

    typer.echo(
        f"Notas:     "
        f"{person.notes or '-'}"
    )

    # --------------------------------------------------------
    # Relationship
    # --------------------------------------------------------

    title("Relações")

    for relationship in person.relationships:

        typer.echo(
            f"Tipo:          "
            f"{relationship.relationship_type}"
        )

        typer.echo(
            f"Vínculo:          "
            f"{relationship.bond_level}/5"
        )

        typer.echo(
            f"Vínculo desejado:  "
            f"{relationship.desired_bond_level}/5"
        )

        typer.echo(
            f"Máximo de dias:      "
            f"{relationship.max_days_without_contact}"
        )

    # --------------------------------------------------------
    # Interests
    # --------------------------------------------------------

    title("Interesses")

    typer.echo(
        "Gostos:    "
        + ", ".join(
            get_interest_names(
                person,
                "like",
            )
        )
        or "Gosto:    -"
    )

    typer.echo(
        "Neutro:  "
        + ", ".join(
            get_interest_names(
                person,
                "neutral",
            )
        )
        or "Neutro:  -"
    )

    typer.echo(
        "Desgostos: "
        + ", ".join(
            get_interest_names(
                person,
                "dislike",
            )
        )
        or "Desgosto: -"
    )

    # --------------------------------------------------------
    # Contact
    # --------------------------------------------------------

    title("Contact")

    if person.interactions:

        latest = max(
            person.interactions,
            key=lambda x: x.occurred_at,
        )

        days = (
            today - latest.occurred_at.date()
        ).days

        typer.echo(
            f"Último contato: "
            f"{latest.occurred_at:%Y-%m-%d %H:%M}"
        )

        typer.echo(
            f"Dias atrás:     "
            f"{days}"
        )

        if person.relationships:

            max_days = (
                person.relationships[0]
                .max_days_without_contact
            )

            if (
                max_days is not None
                and days > max_days
            ):
                typer.secho(
                    f"⚠ Você está "
                    f"{days - max_days} dias "
                    f"acima da sua lista de contatos.",
                    fg=typer.colors.YELLOW,
                )

    else:

        typer.echo(
            "Nenhum contato gravado."
        )


# ============================================================
# UPDATE
# ============================================================

@app.command()
def update():
    """
    Encontra uma pessoa e interativamente escolha o que atualizar.
    """

    with get_session() as session:

        person = choose_person(
            session
        )

        if person is None:
            return

        while True:

            choice = menu(
                f"Update {person.name}",
                [
                    "Informação básica",
                    "Relações",
                    "Interesses",
                    "Savar and sair",
                ],
            )

            # ------------------------------------------------
            # Basic
            # ------------------------------------------------

            if choice == 0:

                title("Informação básica")

                person.name = (
                    ask_text(
                        "Nome",
                        person.name,
                    )
                    or person.name
                )

                person.birthday = ask_date(
                    "Aniversário",
                    person.birthday,
                )

                person.cellphone = ask_text(
                    "Telefone",
                    person.cellphone,
                )

                person.email = ask_text(
                    "Email",
                    person.email,
                )

                person.photo_path = ask_text(
                    "Localização de foto",
                    person.photo_path,
                )

                person.notes = ask_text(
                    "Notas",
                    person.notes,
                )

            # ------------------------------------------------
            # Relationship
            # ------------------------------------------------

            elif choice == 1:

                title("Relacionamento")

                if person.relationships:

                    relationship = (
                        person.relationships[0]
                    )

                else:

                    relationship = (
                        PersonRelationship(
                            person_id=person.id,
                            relationship_type="amigo",
                            bond_level=5,
                            desired_bond_level=5,
                            max_days_without_contact=14,
                        )
                    )

                    session.add(
                        relationship
                    )

                relationship.relationship_type = (
                    ask_text(
                        "Tipo",
                        relationship.relationship_type,
                    )
                )

                relationship.bond_level = ask_int(
                    "Vínculo",
                    relationship.bond_level,
                    0,
                    10,
                )

                relationship.desired_bond_level = (
                    ask_int(
                        "Vínculo desejado",
                        relationship.desired_bond_level,
                        0,
                        10,
                    )
                )

                relationship.max_days_without_contact = (
                    ask_int(
                        "Máximo dias sem entrar em contato",
                        relationship.max_days_without_contact,
                        1,
                    )
                )

            # ------------------------------------------------
            # Interests
            # ------------------------------------------------

            elif choice == 2:

                title("Interesses")

                likes = ask_list(
                    "Gosta de",
                    get_interest_names(
                        person,
                        "like",
                    ),
                )

                neutral = ask_list(
                    "Neutro em",
                    get_interest_names(
                        person,
                        "neutral",
                    ),
                )

                dislikes = ask_list(
                    "Não gosta de",
                    get_interest_names(
                        person,
                        "dislike",
                    ),
                )

                replace_interests(
                    session,
                    person,
                    likes,
                    neutral,
                    dislikes,
                )

            # ------------------------------------------------
            # Save
            # ------------------------------------------------

            elif choice == 3:

                session.commit()

                typer.secho(
                    "\n✓ Mudanças salvas.",
                    fg=typer.colors.GREEN,
                )

                return


# ============================================================
# DELETE
# ============================================================

@app.command()
def delete():
    """
    Escolha uma pessoa e exclui ele.
    """

    with get_session() as session:

        person = choose_person(
            session
        )

        if person is None:
            return

        title(
            f"Deletar {person.name}"
        )

        typer.echo(
            "Isso ira remover permanentemente "
            "as informações dessa pessoas e seus dados."
        )

        typer.echo("")

        if not confirm(
            f"Excluir {person.name}?"
        ):
            typer.echo(
                "Cancelado."
            )
            return

        session.delete(
            person
        )

        session.commit()

        typer.secho(
            f"✓ {person.name} excluído.",
            fg=typer.colors.GREEN,
        )



# ============================================================
# LIST
# ============================================================

@app.command("list")
def list_people():
    """
    Pesquisa pessoas de maneira interativa.
    """

    with get_session() as session:

        while True:

            query = typer.prompt(
                "\nProcurar por nome "
                "(ENTER para listar todos, q para sair)",
                default="",
                show_default=False,
            ).strip()

            if query.lower() == "q":
                return

            people = find_people(
                session,
                query,
            )

            if not people:
                typer.echo(
                    "No people found."
                )
                continue

            options = [
                person.name
                for person in people
            ]

            options.append(
                "Voltar"
            )

            choice = menu(
                "Pessoas",
                options,
            )

            if choice == len(options) - 1:
                return

            person = load_person(
                session,
                people[choice].id,
            )

            display_person(
                person
            )

            pause()


# ============================================================
# CONTACT
# ============================================================

@app.command()
def contact():
    """
    Grava uma interação com alguem.
    """

    with get_session() as session:

        person = choose_person(
            session
        )

        if person is None:
            return

        title(
            f"Interagiu com {person.name}"
        )

        interaction_type = ask_text(
            "Tipo",
            "Conversa",
        )

        occurred_at = typer.prompt(
            "Quando [YYYY-MM-DD HH:MM]",
            default=datetime.now().strftime(
                "%Y-%m-%d %H:%M"
            ),
        )

        notes = ask_text(
            "Notas"
        )

        try:
            timestamp = datetime.fromisoformat(
                occurred_at
            )
        except ValueError:

            typer.secho(
                "Invalid date/time.",
                fg=typer.colors.RED,
            )

            return

        interaction = Interaction(
            person_id=person.id,
            occurred_at=timestamp,
            interaction_type=interaction_type,
            notes=notes,
        )

        session.add(
            interaction
        )

        session.commit()

        typer.secho(
            f"\n✓ Interação com "
            f"{person.name} gravado.",
            fg=typer.colors.GREEN,
        )


# ============================================================
# INTERACTIVE HOME
# ============================================================

@app.command("menu")
def interactive_menu():
    """
    Abra a aplicação interação.
    """

    while True:

        title(
            "Hypno: Orgazinador de vida pessoal."
        )

        choice = menu(
            "O que você gostária de fazer?",
            [
                "Pessoas",
                "Adicionar uma pessoa",
                "Gravar interação",
                "Sair",
            ],
        )

        if choice == 0:
            list_people()

        elif choice == 1:
            create()

        elif choice == 2:
            contact()

        elif choice == 3:
            typer.echo(
                "\nTchau =)!"
            )
            return

# ============================================================
# RECOMENDATION HOME
# ============================================================


def show_score_details(
    result: PriorityResult,
) -> None:
    typer.echo("")
    typer.echo("   Componentes do score:")

    typer.echo(
        f"   contato:     "
        f"{result.contact_score:.2f}"
    )

    typer.echo(
        f"   vínculo:     "
        f"{result.bond_gap_score:.2f}"
    )

    typer.echo(
        f"   atividade:   "
        f"{result.monthly_activity_score:.2f}"
    )

    typer.echo(
        f"   aniversário: "
        f"{result.birthday_score:.2f}"
    )


def show_recommendation(
    position: int,
    result: PriorityResult,
    *,
    details: bool,
) -> None:
    typer.echo(
        f"{position}. {result.person_name} "
        f"— {result.percentage}%"
    )

    for reason in result.reasons:
        typer.echo(
            f"   • {reason}"
        )

    if details:
        show_score_details(result)

    typer.echo("")


@app.callback(invoke_without_command=True)
def recommend(
    ctx: typer.Context,
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        min=1,
        help="Número de pessoas exibidas.",
    ),
    details: bool = typer.Option(
        False,
        "--details",
        "-d",
        help="Exibe detalhes do cálculo.",
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    with SessionLocal() as session:
        recommendations = get_recommendations(
            session,
            limit=limit,
        )

    if not recommendations:
        typer.echo(
            "Nenhuma pessoa cadastrada."
        )
        return

    typer.echo("")
    typer.echo("Recomendações")
    typer.echo("=" * 40)
    typer.echo("")

    for position, result in enumerate(
        recommendations,
        start=1,
    ):
        show_recommendation(
            position,
            result,
            details=details,
        )

def create_digest(
    *,
    limit: int,
    minimum_priority: float,
):
    with get_session() as session:
        return build_daily_digest(
            session,
            limit=limit,
            minimum_priority=minimum_priority,
        )


@app.command()
def preview(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        min=1,
    ),
    minimum_priority: float = typer.Option(
        0.25,
        "--minimum-priority",
        min=0,
        max=1,
    ),
) -> None:
    """
    Exibe o digest sem enviar e-mail.
    """

    digest = create_digest(
        limit=limit,
        minimum_priority=minimum_priority,
    )

    typer.echo(
        render_digest_text(
            digest
        )
    )


@app.command()
def send(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        min=1,
    ),
    minimum_priority: float = typer.Option(
        0.25,
        "--minimum-priority",
        min=0,
        max=1,
    ),
) -> None:
    """
    Gera e envia o digest diário.
    """

    digest = create_digest(
        limit=limit,
        minimum_priority=minimum_priority,
    )

    text = render_digest_text(
        digest
    )

    html = render_digest_html(
        digest
    )

    subject = (
        "Hypno — Digest Social — "
        f"{date.today().strftime('%d/%m/%Y')}"
    )

    try:
        send_email(
            subject=subject,
            text=text,
            html=html,
        )

    except (
        RuntimeError,
        SMTPException,
        OSError,
    ) as error:
        typer.secho(
            f"Erro ao enviar digest: {error}",
            fg=typer.colors.RED,
        )

        raise typer.Exit(
            code=1
        )

    typer.secho(
        "Digest enviado com sucesso.",
        fg=typer.colors.GREEN,
    )

@app.command("email")
def configure_email() -> None:
    email = typer.prompt(
        "E-mail do Gmail"
    )

    recipient = typer.prompt(
        "E-mail que receberá o digest",
        default=email,
    )

    password = typer.prompt(
        "Senha de app do Gmail",
        hide_input=True,
    )

    CONFIG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    config_content = f"""
[email]
provider = "gmail"
username = "{email}"
recipient = "{recipient}"

[smtp]
host = "smtp.gmail.com"
port = 587
security = "starttls"
""".strip()

    CONFIG_PATH.write_text(
        config_content,
        encoding="utf-8",
    )

    keyring.set_password(
        KEYRING_SERVICE,
        email,
        password,
    )

    typer.secho(
        "Configuração de e-mail salva.",
        fg=typer.colors.GREEN,
    )


@app.command("email-test")
def test_email() -> None:
    """
    Testa a conexão SMTP e envia uma mensagem de teste.
    """

    typer.echo(
        "Testando conexão com o servidor SMTP..."
    )

    try:
        test_email_connection()

    except FileNotFoundError:
        typer.secho(
            "Arquivo de configuração não encontrado.",
            fg=typer.colors.RED,
        )

        typer.echo(
            "Execute primeiro: hypno config email"
        )

        raise typer.Exit(
            code=1
        )

    except RuntimeError as error:
        typer.secho(
            f"Erro de configuração: {error}",
            fg=typer.colors.RED,
        )

        raise typer.Exit(
            code=1
        )

    except smtplib.SMTPAuthenticationError:
        typer.secho(
            "Falha na autenticação do Gmail.",
            fg=typer.colors.RED,
        )

        typer.echo(
            "Verifique o endereço de e-mail e a senha de app."
        )

        raise typer.Exit(
            code=1
        )

    except smtplib.SMTPConnectError:
        typer.secho(
            "Não foi possível conectar ao servidor SMTP.",
            fg=typer.colors.RED,
        )

        raise typer.Exit(
            code=1
        )

    except smtplib.SMTPException as error:
        typer.secho(
            f"Erro SMTP: {error}",
            fg=typer.colors.RED,
        )

        raise typer.Exit(
            code=1
        )

    except OSError as error:
        typer.secho(
            f"Erro de rede: {error}",
            fg=typer.colors.RED,
        )

        raise typer.Exit(
            code=1
        )

    typer.secho(
        "Autenticação SMTP funcionando.",
        fg=typer.colors.GREEN,
    )

    send_test = typer.confirm(
        "Deseja enviar um e-mail de teste?",
        default=True,
    )

    if not send_test:
        return

    try:
        send_email(
            subject="Hypno — Teste de e-mail",
            text=(
                "Seu Hypno está configurado corretamente.\n\n"
                "Se você recebeu esta mensagem, "
                "o envio SMTP está funcionando."
            ),
            html="""
            <html>
                <body>
                    <h2>Hypno</h2>

                    <p>
                        Seu Hypno está configurado
                        corretamente.
                    </p>

                    <p>
                        Se você recebeu esta mensagem,
                        o envio SMTP está funcionando.
                    </p>
                </body>
            </html>
            """,
        )

    except (
        smtplib.SMTPException,
        RuntimeError,
        OSError,
    ) as error:
        typer.secho(
            f"Conexão funcionou, mas o envio falhou: {error}",
            fg=typer.colors.RED,
        )

        raise typer.Exit(
            code=1
        )

    typer.secho(
        "E-mail de teste enviado.",
        fg=typer.colors.GREEN,
    )
# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    run()
