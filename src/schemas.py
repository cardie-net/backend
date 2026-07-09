from typing import List, Literal, Union

from pydantic import BaseModel


# Define the element types that can be on a card face
class TextElement(BaseModel):
    type: Literal["text"]
    content: str


# Union of all possible element types (currently just text)
CardElement = Union[TextElement]


class CardBase(BaseModel):
    front: List[CardElement]
    back: List[CardElement]


class CardCreate(CardBase):
    pass


class Card(CardBase):
    id: int
    deck_id: int

    class Config:
        from_attributes = True


class DeckBase(BaseModel):
    name: str
    slug: str


class DeckCreate(DeckBase):
    pass


class Deck(DeckBase):
    id: int
    user_id: int
    cards: List[Card] = []

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    email: str


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int
    is_active: bool
    decks: List[Deck] = []

    class Config:
        from_attributes = True
