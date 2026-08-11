import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from .. import models


async def record_daily_activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    points: int,
    count: int = 1,
    activity_type: str | None = None,
    date_str: str | None = None,
) -> models.UserDailyActivity:
    """Record or update user daily activity points."""
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    result = await db.execute(
        select(models.UserDailyActivity).where(
            models.UserDailyActivity.user_id == user_id,
            models.UserDailyActivity.date == date_str,
        )
    )
    activity = result.scalars().first()

    if activity:
        activity.points += points
        activity.activities_count += count
        if activity_type:
            details = dict(activity.details) if activity.details else {}
            details[activity_type] = details.get(activity_type, 0) + points
            activity.details = details
            flag_modified(activity, "details")
    else:
        details = {activity_type: points} if activity_type else {}
        activity = models.UserDailyActivity(
            user_id=user_id,
            date=date_str,
            points=points,
            activities_count=count,
            details=details,
        )
        db.add(activity)

    await db.commit()
    await db.refresh(activity)
    return activity


async def get_user_activity_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    days: int = 365,
) -> models.UserActivitySummary:
    """Retrieve activity history and summary stats for a user over the past N days."""
    today = datetime.now(timezone.utc).date()
    start_date = (today - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    result = await db.execute(
        select(models.UserDailyActivity)
        .where(
            models.UserDailyActivity.user_id == user_id,
            models.UserDailyActivity.date >= start_date,
        )
        .order_by(models.UserDailyActivity.date.asc())
    )
    records = list(result.scalars().all())

    active_dates: set[str] = {r.date for r in records if r.points > 0}
    total_points = sum(r.points for r in records)
    total_active_days = len(active_dates)

    # Calculate streaks
    current_streak = 0
    check_date = today

    # Check today. If today is active, streak starts with today.
    # If today is not active yet, check yesterday to see if active streak continues.
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    if today_str in active_dates:
        check_date = today
    elif yesterday_str in active_dates:
        check_date = today - timedelta(days=1)
    else:
        check_date = None

    if check_date:
        while check_date.strftime("%Y-%m-%d") in active_dates:
            current_streak += 1
            check_date -= timedelta(days=1)

    # Calculate longest streak
    longest_streak = 0
    if active_dates:
        sorted_dates = sorted(
            datetime.strptime(d, "%Y-%m-%d").date() for d in active_dates
        )
        temp_streak = 1
        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i - 1] + timedelta(days=1):
                temp_streak += 1
            else:
                if temp_streak > longest_streak:
                    longest_streak = temp_streak
                temp_streak = 1
        longest_streak = max(longest_streak, temp_streak)

    activities_read = [
        models.UserDailyActivityRead(
            id=r.id,
            user_id=r.user_id,
            date=r.date,
            points=r.points,
            activities_count=r.activities_count,
            details=r.details,
        )
        for r in records
    ]

    return models.UserActivitySummary(
        activities=activities_read,
        total_points=total_points,
        current_streak=current_streak,
        longest_streak=longest_streak,
        total_active_days=total_active_days,
    )
