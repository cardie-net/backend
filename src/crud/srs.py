import uuid
from datetime import date, timedelta
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..models import (
    Card,
    Deck,
    SRSCardProgress,
    SRSCardProgressRead,
    SRSDeckCounts,
    SRSReviewItem,
    SRSStudyResponse,
)


def compute_srs_schedule(
    rating: int, current_reps: int, current_interval: float, current_ef: float
) -> tuple[int, float, float]:
    """Compute next interval using modified SM-2 algorithm."""
    new_reps = current_reps
    new_interval = current_interval
    new_ef = current_ef

    if rating == 0:
        new_reps = 0
        new_interval = 1.0
    elif rating == 1:
        new_interval = max(1.0, current_interval * 1.2)
    elif rating == 2:
        if current_reps == 0:
            new_interval = 1.0
        elif current_reps == 1:
            new_interval = 6.0
        else:
            new_interval = current_interval * current_ef
        new_reps += 1
    elif rating == 3:
        if current_reps == 0:
            new_interval = 4.0
        elif current_reps == 1:
            new_interval = 10.0
        else:
            new_interval = current_interval * current_ef * 1.3
        new_reps += 1

    new_ef = current_ef + (0.1 - (3 - rating) * (0.08 + (3 - rating) * 0.02))
    new_ef = max(1.3, new_ef)

    return new_reps, new_interval, new_ef


async def get_srs_counts_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> Dict[uuid.UUID, SRSDeckCounts]:
    """Get SRS counts for all decks owned by the user."""
    today = date.today().isoformat()

    # Get all decks owned by user
    decks_result = await db.execute(select(Deck.id).where(Deck.user_id == user_id))
    deck_ids = decks_result.scalars().all()

    counts: Dict[uuid.UUID, SRSDeckCounts] = {}

    for deck_id in deck_ids:
        # Get all cards in deck
        cards_result = await db.execute(select(Card.id).where(Card.deck_id == deck_id))
        card_ids = cards_result.scalars().all()

        if not card_ids:
            counts[deck_id] = SRSDeckCounts(
                new_count=0, learning_count=0, review_count=0
            )
            continue

        # Get SRS progress for these cards for this user
        progress_result = await db.execute(
            select(SRSCardProgress).where(
                SRSCardProgress.user_id == user_id,
                SRSCardProgress.card_id.in_(card_ids),
            )
        )
        progress_list = progress_result.scalars().all()
        progress_by_card = {p.card_id: p for p in progress_list}

        new_count = 0
        learning_count = 0
        review_count = 0

        for cid in card_ids:
            p = progress_by_card.get(cid)
            if not p:
                new_count += 1
            elif p.repetitions == 0 and p.due_date and p.due_date <= today:
                learning_count += 1
            elif p.repetitions >= 1 and p.due_date and p.due_date <= today:
                review_count += 1

        # Apply limits
        new_count = min(10, new_count)
        review_count = min(100, review_count)

        counts[deck_id] = SRSDeckCounts(
            new_count=new_count,
            learning_count=learning_count,
            review_count=review_count,
        )

    return counts


async def get_srs_study_cards(
    db: AsyncSession, user_id: uuid.UUID, deck_id: uuid.UUID, today: str
) -> SRSStudyResponse:
    # Get all cards in deck
    cards_result = await db.execute(select(Card.id).where(Card.deck_id == deck_id))
    card_ids = cards_result.scalars().all()

    if not card_ids:
        return SRSStudyResponse(new_cards=[], learning_cards=[], review_cards=[])

    progress_result = await db.execute(
        select(SRSCardProgress).where(
            SRSCardProgress.user_id == user_id,
            SRSCardProgress.card_id.in_(card_ids),
        )
    )
    progress_list = progress_result.scalars().all()
    progress_by_card = {p.card_id: p for p in progress_list}

    new_cards = []
    learning_cards = []
    review_cards = []

    for cid in card_ids:
        p = progress_by_card.get(cid)
        if not p:
            if len(new_cards) < 10:
                new_cards.append(
                    SRSCardProgressRead(
                        card_id=cid,
                        repetitions=0,
                        ease_factor=2.5,
                        interval=0.0,
                        due_date=None,
                        last_reviewed=None,
                    )
                )
        elif p.repetitions == 0 and p.due_date and p.due_date <= today:
            learning_cards.append(
                SRSCardProgressRead(
                    card_id=p.card_id,
                    repetitions=p.repetitions,
                    ease_factor=p.ease_factor,
                    interval=p.interval,
                    due_date=p.due_date,
                    last_reviewed=p.last_reviewed,
                )
            )
        elif p.repetitions >= 1 and p.due_date and p.due_date <= today:
            if len(review_cards) < 100:
                review_cards.append(
                    SRSCardProgressRead(
                        card_id=p.card_id,
                        repetitions=p.repetitions,
                        ease_factor=p.ease_factor,
                        interval=p.interval,
                        due_date=p.due_date,
                        last_reviewed=p.last_reviewed,
                    )
                )

    return SRSStudyResponse(
        new_cards=new_cards,
        learning_cards=learning_cards,
        review_cards=review_cards,
    )


async def process_srs_reviews(
    db: AsyncSession,
    user_id: uuid.UUID,
    deck_id: uuid.UUID,
    reviews: list[SRSReviewItem],
    today: str,
) -> None:
    # Get all cards in deck to validate
    cards_result = await db.execute(select(Card.id).where(Card.deck_id == deck_id))
    valid_card_ids = set(cards_result.scalars().all())

    today_date = date.fromisoformat(today)

    for review in reviews:
        if review.card_id not in valid_card_ids:
            continue

        progress_result = await db.execute(
            select(SRSCardProgress).where(
                SRSCardProgress.user_id == user_id,
                SRSCardProgress.card_id == review.card_id,
            )
        )
        progress = progress_result.scalar_one_or_none()

        if not progress:
            progress = SRSCardProgress(
                user_id=user_id,
                card_id=review.card_id,
                repetitions=0,
                ease_factor=2.5,
                interval=0.0,
                due_date=today,
                last_reviewed=None,
            )
            db.add(progress)

        new_reps, new_interval, new_ef = compute_srs_schedule(
            rating=review.rating,
            current_reps=progress.repetitions,
            current_interval=progress.interval,
            current_ef=progress.ease_factor,
        )

        progress.repetitions = new_reps
        progress.interval = new_interval
        progress.ease_factor = new_ef
        progress.last_reviewed = today
        progress.due_date = (today_date + timedelta(days=new_interval)).isoformat()

    await db.commit()
