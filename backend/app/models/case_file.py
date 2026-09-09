"""Case File data contract - the permanent source of user-confirmed and
document-confirmed facts about a project (product scope doc, section B.4).

This schema is deliberately close to the JSON shape in the scope document so
that a report generator, a future export layer, and later phases (which only
ever *extend* this contract per section A.4) can all agree on field names.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OccupancyType(str, Enum):
    RESIDENTIAL = "Residential"
    EDUCATIONAL = "Educational"
    INSTITUTIONAL = "Institutional"
    ASSEMBLY = "Assembly"
    BUSINESS = "Business"
    MERCANTILE = "Mercantile"
    INDUSTRIAL = "Industrial"
    STORAGE = "Storage"
    HAZARDOUS = "Hazardous"
    MIXED_USE = "Mixed Use"


class IndustrialHazardBand(str, Enum):
    G1_LOW = "G-1"
    G2_MODERATE = "G-2"
    G3_HIGH = "G-3"


class ProjectStage(str, Enum):
    CONCEPT = "concept"
    PLAN_SUBMITTED = "plan_submitted"
    UNDER_CONSTRUCTION = "under_construction"
    RENEWAL = "renewal"


class Goal(str, Enum):
    UNDERSTAND_REQUIREMENTS = "understand_requirements"
    PREP_NOC = "prep_noc"
    RENEW_NOC = "renew_noc"
    GENERAL_QA = "general_qa"


class ConversationStage(str, Enum):
    INTAKE = "intake"
    CONFIRMING = "confirming"
    CLASSIFIED = "classified"
    REPORT_READY = "report_ready"


class CodeEdition(str, Enum):
    NBCS_2026 = "2026"
    NBC_2016 = "2016"


class FieldSourceKind(str, Enum):
    USER = "user"
    DOCUMENT = "document"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class OccupancyBreakdownItem(BaseModel):
    """One component of a mixed-occupancy building (B.4).

    floor_area_sqm is an addition beyond the original B.4 schema: Table 7's
    bands are height/area-driven, so classifying a single component requires
    its own floor area even though the whole building shares one height_m.
    Optional because the union-of-clauses logic (see
    app/engine/classifier.py's classify_mixed_use) still degrades to "flag
    for human review" rather than guessing when it's missing for a component.
    """

    type: OccupancyType
    floor_range: str
    floor_area_sqm: Optional[float] = None
    subdivision: Optional[str] = Field(
        default=None,
        description=(
            "Same purpose as CaseFile.occupancy_subdivision, but per-component: "
            "needed when this component's occupancy type is one of the ones "
            "whose Table 7 has multiple genuinely different subdivisions "
            "(see occupancy_subdivision's docstring)."
        ),
    )


class FloorAreaItem(BaseModel):
    """One row of a floor-wise area breakdown - an addition beyond the
    original B.4 schema (which only has a single built_up_area_sqm total).
    Added because architectural drawings' "area statement" schedules give
    area per floor, not just a building total, and that's useful to capture
    even though today's digitized NBCS Table 7 lookups still key off the
    single built_up_area_sqm total (see classifier.py) - this is
    informational/report-facing only, not a classification input, per an
    explicit product decision to not invent NBCS clause logic that doesn't
    exist in the digitized rule data.
    """

    floor: str
    area_sqm: float


class SourceDocument(BaseModel):
    filename: str
    pages: int = 0
    extraction_tier_used: Optional[int] = Field(
        default=None, ge=1, le=5, description="1-5, see B.7 tiered OCR pipeline"
    )
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class FieldSource(BaseModel):
    value: object = None
    source: FieldSourceKind = FieldSourceKind.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ClassificationResult(BaseModel):
    applies: Optional[bool] = None
    table_7_ref: str = ""
    applicable_clauses: list[str] = Field(default_factory=list)
    applicable_state_checklist_id: Optional[str] = None
    is_high_rise: Optional[bool] = None
    require_human_review_flag: bool = False
    protection_level: Optional[str] = Field(
        default=None, description="e.g. 'HL-3' or 'CL-4' from Table 7A-7J"
    )
    notes: list[str] = Field(default_factory=list)


class CaseFile(BaseModel):
    session_id: str
    project_name: str = ""
    state: str = ""
    city: str = ""

    occupancy_type: Optional[OccupancyType] = None
    occupancy_subdivision: Optional[str] = Field(
        default=None,
        description=(
            "NBCS subdivision code where Table 7's bands genuinely differ by "
            "subdivision (e.g. 'A-I' lodging house vs 'A-V' starred hotel "
            "within Residential; 'C-I' hospitals vs 'C-II_C-III' custodial/"
            "penal within Institutional; 'E-I'/'E-II' human-occupied vs "
            "datacentre within Business; 'F'/'F-II' vs underground shopping "
            "within Mercantile). NOT part of the original B.4 schema in the "
            "product scope document - added because the classifier cannot "
            "safely pick a Table 7 band without it for these occupancies. "
            "Industrial does not need this field; use industrial_hazard_band."
        ),
    )
    industrial_hazard_band: Optional[IndustrialHazardBand] = None
    mixed_occupancy: bool = False
    occupancy_breakdown: list[OccupancyBreakdownItem] = Field(default_factory=list)

    height_m: Optional[float] = None
    is_high_rise: Optional[bool] = None
    floors_above_ground: Optional[int] = None
    floors_below_ground: Optional[int] = None
    built_up_area_sqm: Optional[float] = None
    floor_wise_area: list[FloorAreaItem] = Field(default_factory=list)
    number_of_staircases: Optional[int] = None
    number_of_exits: Optional[int] = None
    existing_fire_systems: list[str] = Field(default_factory=list)

    project_stage: Optional[ProjectStage] = None
    goal: Optional[Goal] = None

    code_edition: CodeEdition = Field(
        default=CodeEdition.NBCS_2026,
        description=(
            "Which code edition governs this case. Defaults to 2026 (the "
            "live/primary source) unless the case involves a building "
            "certified under 2016 and not yet reassessed."
        ),
    )

    source_documents: list[SourceDocument] = Field(default_factory=list)
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)

    classification_result: ClassificationResult = Field(
        default_factory=ClassificationResult
    )

    conversation_stage: ConversationStage = ConversationStage.INTAKE

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
