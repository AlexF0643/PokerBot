import random

import pytest

from pokerbot import Card, Deck, parse_cards


def test_all_cards_round_trip_through_text():
    for card_id in range(52):
        card = Card(card_id)
        assert Card.parse(str(card)) == card


def test_rank_and_suit():
    ace_of_spades = Card.parse("As")
    assert ace_of_spades == 51
    assert ace_of_spades.rank == 12
    assert ace_of_spades.suit == 3
    assert Card.parse("2c") == 0


def test_parse_is_case_insensitive():
    assert Card.parse("aS") == Card.parse("As")


@pytest.mark.parametrize("text", ["", "A", "Asd", "1s", "Ax"])
def test_parse_rejects_invalid_text(text):
    with pytest.raises(ValueError):
        Card.parse(text)


@pytest.mark.parametrize("card_id", [-1, 52])
def test_card_rejects_out_of_range_ids(card_id):
    with pytest.raises(ValueError):
        Card(card_id)


def test_parse_cards_with_and_without_spaces():
    expected = [Card.parse("As"), Card.parse("Kd")]
    assert parse_cards("As Kd") == expected
    assert parse_cards("AsKd") == expected
    assert parse_cards("") == []


def test_parse_cards_rejects_odd_length():
    with pytest.raises(ValueError):
        parse_cards("AsK")


def test_deck_deals_every_card_once():
    deck = Deck()
    assert len(deck) == 52
    assert sorted(deck.deal(52)) == list(range(52))
    assert len(deck) == 0


def test_deck_shuffle_is_reproducible_with_a_seed():
    first = Deck(random.Random(7)).deal(52)
    second = Deck(random.Random(7)).deal(52)
    assert first == second
    assert first != sorted(first)


def test_deck_excludes_known_cards():
    known = parse_cards("As Kd")
    deck = Deck(exclude=known)
    assert len(deck) == 50
    assert not set(known) & set(deck.deal(50))


def test_deal_zero_returns_nothing():
    deck = Deck()
    assert deck.deal(0) == []
    assert len(deck) == 52


@pytest.mark.parametrize("count", [-1, 53])
def test_deal_rejects_invalid_counts(count):
    with pytest.raises(ValueError):
        Deck().deal(count)
