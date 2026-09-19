from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    birthday: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    cellphone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    photo_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    interests: Mapped[list["PersonInterest"]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
    )

    interactions: Mapped[list["Interaction"]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
    )

    relationships: Mapped[list["PersonRelationship"]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
    )


class Interest(Base):
    __tablename__ = "interests"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    people: Mapped[list["PersonInterest"]] = relationship(
        back_populates="interest",
    )


class PersonInterest(Base):
    __tablename__ = "person_interests"

    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"),
        primary_key=True,
    )

    interest_id: Mapped[int] = mapped_column(
        ForeignKey("interests.id", ondelete="CASCADE"),
        primary_key=True,
    )

    sentiment: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "sentiment IN ('like', 'neutral', 'dislike')",
            name="valid_sentiment",
        ),
    )

    person: Mapped["Person"] = relationship(
        back_populates="interests",
    )

    interest: Mapped["Interest"] = relationship(
        back_populates="people",
    )


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    interaction_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    person: Mapped["Person"] = relationship(
        back_populates="interactions",
    )


class PersonRelationship(Base):
    __tablename__ = "person_relationships"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    relationship_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    bond_level: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    desired_bond_level: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    max_days_without_contact: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "bond_level IS NULL OR "
            "(bond_level >= 0 AND bond_level <= 10)",
            name="valid_bond_level",
        ),
        CheckConstraint(
            "desired_bond_level IS NULL OR "
            "(desired_bond_level >= 0 AND desired_bond_level <= 10)",
            name="valid_desired_bond_level",
        ),
        CheckConstraint(
            "max_days_without_contact IS NULL OR "
            "max_days_without_contact > 0",
            name="valid_contact_interval",
        ),
    )

    person: Mapped["Person"] = relationship(
        back_populates="relationships",
    )