"""Streaming services: the public registry + the user's saved selection.

``GET /providers`` powers the onboarding buttons (and reports whether per-title
availability data is loaded). ``GET/PUT /account/providers`` read and write the
signed-in user's services, flipping ``onboarding_completed`` so the one-time
screen never reappears.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth.deps import get_current_user
from db.database import User, UserProvider, get_db
from dependencies import get_provider_index
from providers import CANONICAL_IDS, CANONICAL_PROVIDERS, ProviderIndex
from schemas import ProviderInfo, ProvidersResponse, UserProvidersResponse, UserProvidersUpdate

router = APIRouter(tags=["providers"])


def user_provider_ids(db: Session, user: User | None) -> list[int]:
    """The user's saved provider ids (empty for guests / no selection).

    Shared by the deck routes: a signed-in user's saved services override
    whatever provider list the client sent.
    """
    if user is None:
        return []
    return list(db.scalars(select(UserProvider.provider_id).where(UserProvider.user_id == user.id)))


@router.get("/providers", response_model=ProvidersResponse)
def list_providers(index: ProviderIndex = Depends(get_provider_index)) -> ProvidersResponse:
    """Return the selectable streaming services and availability-data status."""
    return ProvidersResponse(
        providers=[ProviderInfo(id=p.id, slug=p.slug, name=p.name, color=p.color) for p in CANONICAL_PROVIDERS],
        availability_loaded=index.has_data,
        region=index.region,
    )


@router.get("/account/providers", response_model=UserProvidersResponse)
def my_providers(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserProvidersResponse:
    """Return the signed-in user's saved services + onboarding state."""
    return UserProvidersResponse(
        providers=sorted(user_provider_ids(db, user)),
        onboarding_completed=bool(user.onboarding_completed),
    )


@router.put("/account/providers", response_model=UserProvidersResponse)
def set_my_providers(
    payload: UserProvidersUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProvidersResponse:
    """Replace the user's saved services (unknown ids are dropped).

    Called by the onboarding screen (which also completes onboarding — saving
    *or* skipping) and by the account-menu editor.
    """
    selected = sorted(set(payload.providers) & CANONICAL_IDS)
    db.execute(delete(UserProvider).where(UserProvider.user_id == user.id))
    db.add_all(UserProvider(user_id=user.id, provider_id=pid) for pid in selected)
    if payload.complete:
        user.onboarding_completed = True
    db.commit()
    return UserProvidersResponse(providers=selected, onboarding_completed=bool(user.onboarding_completed))
