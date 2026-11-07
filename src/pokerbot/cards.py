"""Playing cards and the deck.

A card is an int from 0 to 51, equal to ``rank * 4 + suit``, so simulations can
treat cards as plain integers. Ranks run from 0 (two) to 12 (ace).
"""

from __future__ import annotations

import random
from collections.abc import Iterable

RANK_CHARS = "23456789TJQKA"
SUIT_CHARS = "cdhs"


class Card(int):
    """A playing card that behaves as its integer id."""

    __slots__ = ()

    def __new__(cls, card_id: int) -> Card:
        if not 0 <= card_id < 52:
            raise ValueError(f"card id must be in 0..51, got {card_id}")
        return super().__new__(cls, card_id)

    @classmethod
    def parse(cls, text: str) -> Card:
        """Build a card from text such as ``"As"`` or ``"Td"``."""
        if len(text) != 2:
            raise ValueError(f"invalid card: {text!r}")
        rank = RANK_CHARS.find(text[0].upper())
        suit = SUIT_CHARS.find(text[1].lower())
        if rank < 0 or suit < 0:
            raise ValueError(f"invalid card: {text!r}")
        return cls(rank * 4 + suit)

    @property
    def rank(self) -> int:
        return self >> 2

    @property
    def suit(self) -> int:
        return self & 3

    def __str__(self) -> str:
        return RANK_CHARS[self.rank] + SUIT_CHARS[self.suit]

    def __repr__(self) -> str:
        return f"Card({str(self)!r})"


def parse_cards(text: str) -> list[Card]:
    """Parse cards from text, with or without spaces: ``"As Kd"`` or ``"AsKd"``."""
    compact = "".join(text.split())
    if len(compact) % 2:
        raise ValueError(f"invalid card string: {text!r}")
    return [Card.parse(compact[i : i + 2]) for i in range(0, len(compact), 2)]


class Deck:
    """A shuffled deck, optionally excluding cards that are already known."""

    def __init__(
        self,
        rng: random.Random | None = None,
        exclude: Iterable[int] = (),
    ) -> None:
        excluded = set(exclude)
        self._cards = [Card(i) for i in range(52) if i not in excluded]
        (rng or random.Random()).shuffle(self._cards)

    def __len__(self) -> int:
        return len(self._cards)

    def deal(self, count: int = 1) -> list[Card]:
        """Remove ``count`` cards from the deck and return them."""
        if count < 0:
            raise ValueError(f"cannot deal {count} cards")
        if count > len(self._cards):
            raise ValueError(f"cannot deal {count} cards from {len(self._cards)}")
        dealt = self._cards[-count:] if count else []
        if count:
            del self._cards[-count:]
        return dealt
