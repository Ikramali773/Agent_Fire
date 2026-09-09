"""State NOC checklist framework - product scope §B.10.

Loads data/rules/state_checklists/*.json - see that directory's README for
why every file currently ships as an explicit placeholder ("status":
"placeholder", every item a literal "TODO: ...") rather than real Gujarat/
Maharashtra government checklist content: nobody has yet supplied the
source documents, and inventing checklist items that *look* official for a
compliance product would be actively harmful. This module is the framework
that real content drops into later without any code change here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

# backend/app/engine/state_checklists.py -> repo_root/data/rules/state_checklists
_REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKLISTS_DIR = _REPO_ROOT / "data" / "rules" / "state_checklists"

_STATE_TO_FILENAME = {
    "Gujarat": "gujarat.json",
    "Maharashtra": "maharashtra.json",
}


@lru_cache(maxsize=None)
def get_checklist_for_state(state: str) -> Optional[dict]:
    """Returns the checklist dict for a state, or None if this deployment
    doesn't have one yet (any state other than the current launch states).
    Matching is case-insensitive since case_file.state is free-text the user
    typed, not a validated enum (product scope doesn't make state a closed
    list at the Case File level).
    """
    filename = next(
        (fname for name, fname in _STATE_TO_FILENAME.items() if name.lower() == state.strip().lower()),
        None,
    )
    if filename is None:
        return None
    path = CHECKLISTS_DIR / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def checklist_id_for_state(state: str) -> Optional[str]:
    """Convenience for the classifier: just the ID to attach to
    ClassificationResult.applicable_state_checklist_id, or None. Note this
    ID is always the placeholder-suffixed one until real content replaces
    the corresponding data file - it is NOT a claim that a real government
    checklist ID is known.
    """
    if not state:
        return None
    checklist = get_checklist_for_state(state)
    return checklist["checklist_id"] if checklist else None
