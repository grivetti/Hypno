# Hypno

`Hypno` is a personal social relationship management system built with Python, Typer, SQLAlchemy, and SQLite.

The goal of the project is to help track relationships, interactions, interests, birthdays, and desired levels of contact, then use that information to recommend who you may want to interact with and why.

The application also generates a daily social digest and can send it by email.

---

## Features

* Manage people through a CLI
* Store data locally in SQLite
* Track interactions with each person
* Track interests and preferences
* Track current and desired relationship strength
* Define maximum desired time without contact
* Calculate social interaction priority
* Rank people by interaction priority
* Explain why a person received a given priority
* Detect upcoming birthdays
* Track monthly interaction activity
* Generate a daily social digest
* Send the digest by email
* Configure Gmail SMTP credentials securely
* Store email passwords using the operating system keyring
* Preview the digest before sending it

---

## Tech Stack

* Python 3.12+
* Typer
* SQLAlchemy 2.x
* SQLite
* Keyring
* SMTP
* TOML configuration

```bash
git clone <repository-url>
cd hypno
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it.

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows:

```powershell
.venv\Scripts\activate
```

Install it with:

```bash
pip install -e .
```

---

# Database

The application stores its database at:

```text
~/.life/life.db
```

The database is initialized when the CLI starts.

---

# Data Model

## Person

Represents a person in the system.

Fields include:

* name
* birthday
* cellphone
* email
* photo
* notes
* interests
* interactions
* relationships

---

## Interest

Represents a subject a person may like, dislike, or feel neutral about.

Examples:

```text
Photography
Formula 1
Cinema
Programming
Hiking
Books
```

A person's relationship with an interest is stored through `PersonInterest`.

Supported sentiments:

```text
like
neutral
dislike
```

---

## Interaction

Represents an interaction with a person.

Examples:

* message
* phone call
* meeting
* dinner
* event
* online conversation

Each interaction contains:

```text
person
date/time
interaction type
notes
```

---

## PersonRelationship

Represents one type of relationship with a person.

For example:

```text
friend
coworker
family
classmate
neighbor
```

The model tracks:

```text
relationship_type
bond_level
desired_bond_level
max_days_without_contact
```

Bond levels range from:

```text
0 → 10
```

Example:

```text
Current bond: 5
Desired bond: 8
Maximum time without contact: 14 days
```

---

# Priority System

The application calculates a priority score for each person.

The score is based on several factors:

```text
time without contact
relationship gap
monthly interaction activity
upcoming birthday
```

Example weighting:

```text
contact urgency       50%
relationship gap      20%
monthly activity      15%
birthday proximity    15%
```

The final score ranges from:

```text
0.0 → 1.0
```

and is shown in the CLI as a percentage.

Example:

```text
Mariana — 78%
```

---

## Contact Urgency

The system compares:

```text
days since last interaction
```

with:

```text
max_days_without_contact
```

For example:

```text
Maximum desired interval: 14 days
Last interaction: 32 days ago
```

This creates a high contact urgency score.

The score stops growing aggressively after the contact interval is exceeded so that extremely old relationships do not automatically dominate the ranking forever.

---

## Relationship Gap

The system compares:

```text
bond_level
```

against:

```text
desired_bond_level
```

Example:

```text
Current: 5
Desired: 8
```

The gap is:

```text
3
```

A larger positive gap increases interaction priority.

If the desired bond is equal to or lower than the current bond, no additional priority is added.

---

## Monthly Activity

The expected number of interactions per month is inferred from:

```text
max_days_without_contact
```

Examples:

```text
7 days  → approximately 4 interactions/month
14 days → approximately 2 interactions/month
30 days → approximately 1 interaction/month
```

The system compares expected activity against actual interactions in the current month.

---

## Birthdays

Birthday proximity contributes to the score when the birthday is within a configured window.

By default:

```text
30 days
```

The closer the birthday, the higher the birthday score.

---

# Recommendations

Run:

```bash
hypno recommend
```

Example output:

```text
Recomendações
========================================

1. Mariana — 78%
   • Contato atrasado em 18 dias (limite: 14).
   • Nenhuma interação neste mês.
   • Vínculo desejado é maior que o atual (5 → 8).

2. João — 54%
   • Última interação há 18 dias.
   • 1 interação neste mês.
   • Aniversário em 5 dias.
```

Limit the number of results:

```bash
hypno recommend -n 5
```

Show detailed score components:

```bash
hypno recommend --details
```

Example:

```text
1. Mariana — 78%

   Componentes do score:
   contato:     1.00
   vínculo:     0.30
   atividade:   1.00
   aniversário: 0.00
```

---

# Daily Digest

The application can generate a daily summary of your social relationships.

Preview it with:

```bash
hypno digest preview
```

Example:

```text
Life — Digest Social — 19/09/2026

RESUMO
------

Pessoas cadastradas: 24
Interações neste mês: 13

PRIORIDADES
-----------

1. Mariana — 78%

Última interação: há 32 dias
Interações neste mês: 0
Frequência desejada: 14 dias
Vínculo atual/desejado: 5 → 8
Interesses: cinema, fotografia

Sugestão:
Retome o contato. Você pode puxar assunto sobre cinema.

ANIVERSÁRIOS
------------

- João: em 4 dias
- Pedro: em 17 dias
```

Limit the number of recommendations:

```bash
hypno digest preview --limit 5
```

Filter by minimum priority:

```bash
hypno digest preview --minimum-priority 0.4
```

---

# Gmail Configuration

The application can send the daily digest using Gmail SMTP.

The recommended approach is:

```text
configuration → ~/.life/config.toml
password      → OS keyring
```

The Gmail password is not stored in the database or TOML configuration.

---

## Gmail App Password

Do not use your regular Google account password.

Create a Google App Password and use it for SMTP authentication.

The Gmail SMTP configuration used by Life is:

```text
Host: smtp.gmail.com
Port: 587
Security: STARTTLS
```

---

# Configure Email

Run:

```bash
hypno email
```

The CLI will ask:

```text
E-mail do Gmail:
E-mail que receberá o digest:
Senha de app do Gmail:
```

The password input is hidden.

Example configuration file:

```text
~/.life/config.toml
```

```toml
[email]
provider = "gmail"
username = "your-email@gmail.com"
recipient = "your-email@gmail.com"

[smtp]
host = "smtp.gmail.com"
port = 587
security = "starttls"
```

The Gmail App Password is stored separately in the operating system keyring.

---

# Test Email Configuration

Run:

```bash
hypno email-test
```

The application will first verify the SMTP authentication.

Example:

```text
Testando conexão com o servidor SMTP...
Autenticação SMTP funcionando.

Deseja enviar um e-mail de teste? [Y/n]: y

E-mail de teste enviado.
```

If authentication fails:

```text
Falha na auten
```
