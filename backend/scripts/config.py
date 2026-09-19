"""Shared configuration for backend operational scripts."""

import os
from threading import Lock
from typing import Any, Callable, Optional

from operation_common import load_backend_environment, resolve_active_tournament_id


load_backend_environment()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ACTIVE_TORNEO_ID = resolve_active_tournament_id()
ACTIVE_TORNEO_NAME = os.environ.get("ACTIVE_TORNEO_NAME") or "Primavera/Verano 2026"


def _create_supabase_client() -> Any:
    """Create the configured client only when database access is requested."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "Supabase credentials are required for database access. "
            "Set SUPABASE_URL and SUPABASE_KEY."
        )

    from supabase import create_client

    return create_client(SUPABASE_URL, SUPABASE_KEY)


class LazySupabaseClient:
    """Compatibility proxy that defers client creation until first use."""

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._client: Optional[Any] = None
        self._lock = Lock()

    def _get_client(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = self._factory()
        return self._client

    def table(self, *args: Any, **kwargs: Any) -> Any:
        return self._get_client().table(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_client(), name)

    def __repr__(self) -> str:
        state = "ready" if self._client is not None else "not initialized"
        return f"<LazySupabaseClient {state}>"


supabase = LazySupabaseClient(_create_supabase_client)

# Authoritative club identity map for operational scripts.
MAPEO_CLUBES = {
    "ARGENTINO": 1, 
    "ATL. PASTEUR": 2, 
    "ATL PASTEUR": 2,
    "ATL. ROBERTS": 3,
    "ATL ROBERTS": 3,
    "CA. PINTENSE": 4, 
    "C A PINTENSE": 4,
    "CASET": 5,
    "DEP. ARENAZA": 6,
    "DEP ARENAZA": 6,
    "DEP. GRAL PINTO": 7,
    "DEP GRAL PINTO": 7,
    "EL LINQUEÑO": 8,
    "JUVENTUD UNIDA": 9,
    "SAN MARTIN": 10,
    "VILLA FRANCIA": 11,
    "CAEL": 12,  # El Linqueño B (ninth division)
}

# Authoritative category membership by club ID.
EQUIPOS_POR_CATEGORIA = {
    1: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],  # First division: all clubs
    2: [8, 2, 4, 7, 5, 9, 1, 3],  # Seventh division
    3: [1, 7, 6, 11, 4, 10, 8, 9, 2],  # Eighth division, including ATL PASTEUR
    4: [1, 12, 4, 7, 8, 10],  # Ninth division uses CAEL
    5: [8, 6, 4, 5, 2, 10, 1, 9, 7, 11, 3],  # Tenth division
}

# Authoritative category names and IDs.
CATEGORIAS = {
    "primera": 1,
    "septima": 2,
    "octava": 3,
    "novena": 4,
    "decima": 5
}
