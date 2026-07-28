"""Owner-facing business settings. Tenancy comes from the Clerk session only."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import CurrentBusiness, SessionDep
from app.schemas import BusinessOut, BusinessUpdate
from app.services.calendar import DEFAULT_BUSINESS_HOURS

router = APIRouter(prefix="/api/business", tags=["business"])


@router.get("", response_model=BusinessOut)
async def get_business(business: CurrentBusiness) -> BusinessOut:
    if not business.business_hours:
        business.business_hours = DEFAULT_BUSINESS_HOURS
    return BusinessOut.model_validate(business)


@router.patch("", response_model=BusinessOut)
async def update_business(
    payload: BusinessUpdate, business: CurrentBusiness, session: SessionDep
) -> BusinessOut:
    updates = payload.model_dump(exclude_unset=True, mode="json")
    for field, value in updates.items():
        setattr(business, field, value)
    await session.flush()
    return BusinessOut.model_validate(business)
