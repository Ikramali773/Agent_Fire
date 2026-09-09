"""End-to-end intake conversation test using a scripted fake LLM - proves the
Node 1-7 -> confirm -> classify state machine (dialogue/manager.py) actually
completes and reaches the same deterministic classification the engine tests
verify elsewhere, without any real LLM call.
"""

import uuid

from app.dialogue.manager import handle_turn, start_conversation
from app.llm.client import LLMNotConfiguredError
from app.models.case_file import CaseFile, ConversationStage


class ScriptedLLMClient:
    """Duck-types the LLMClient interface manager.py actually calls."""

    def __init__(self, extractions: dict[str, dict], intents: dict[str, str] | None = None):
        self.extractions = extractions
        self.intents = intents or {}
        self.calls: list[str] = []

    def classify_intent(self, user_text, pending_question):
        self.calls.append(f"classify_intent:{user_text}")
        return self.intents.get(user_text, "answer")

    def extract_fields(self, user_text, field_types, context=""):
        self.calls.append(f"extract_fields:{user_text}")
        return self.extractions.get(user_text, {})

    def answer_question(self, question, knowledge_context, model_tier="reasoning"):
        self.calls.append(f"answer_question:{question}")
        return f"[answer to: {question}]"


def make_case_file() -> CaseFile:
    return CaseFile(session_id=str(uuid.uuid4()))


def test_full_intake_reaches_classification_for_storage_building():
    case_file = make_case_file()
    llm = ScriptedLLMClient(
        extractions={
            "Gujarat, Ahmedabad": {"state": "Gujarat", "city": "Ahmedabad"},
            "just understand requirements": {"goal": "understand_requirements"},
            "Storage": {"occupancy_type": "Storage"},
            "9.5 meters, 1 floor, no basement": {
                "height_m": 9.5,
                "floors_above_ground": 1,
                "floors_below_ground": 0,
            },
            "600 sqm": {"built_up_area_sqm": 600},
            "1 staircase, 2 exits": {"number_of_staircases": 1, "number_of_exits": 2},
            "none yet": {"existing_fire_systems": []},
        }
    )

    start = start_conversation(case_file)
    assert "state and city" in start.agent_message
    case_file = start.case_file

    turns = [
        "Gujarat, Ahmedabad",
        "just understand requirements",
        "Storage",
        "9.5 meters, 1 floor, no basement",
        "600 sqm",
        "1 staircase, 2 exits",
        "none yet",
    ]
    result = None
    for turn in turns:
        result = handle_turn(case_file, turn, llm)
        case_file = result.case_file

    assert case_file.conversation_stage == ConversationStage.CONFIRMING
    assert "correct" in result.agent_message.lower()

    # Confirm turn - no corrections offered, so classify() runs.
    llm.extractions["yes that's right"] = {}
    result = handle_turn(case_file, "yes that's right", llm)
    case_file = result.case_file

    assert case_file.conversation_stage == ConversationStage.CLASSIFIED
    assert case_file.classification_result.applies is True
    assert case_file.classification_result.table_7_ref == "7H"
    assert "7H" in result.agent_message


def test_renewal_goal_nudges_towards_document_upload():
    """Node 2a: answering the goal question with "renew_noc" should prepend
    the upload nudge to the very next agent message (the following node's
    prompt), but a different goal answer should not.
    """
    case_file = make_case_file()
    llm = ScriptedLLMClient(
        extractions={
            "Gujarat, Ahmedabad": {"state": "Gujarat", "city": "Ahmedabad"},
            "renewing my NOC": {"goal": "renew_noc"},
        }
    )
    start_conversation(case_file)
    result = handle_turn(case_file, "Gujarat, Ahmedabad", llm)
    case_file = result.case_file

    result = handle_turn(case_file, "renewing my NOC", llm)

    assert "upload your existing NOC" in result.agent_message
    assert "primary use of the building" in result.agent_message  # still shows the next question


def test_non_renewal_goal_does_not_nudge_upload():
    case_file = make_case_file()
    llm = ScriptedLLMClient(
        extractions={
            "Gujarat, Ahmedabad": {"state": "Gujarat", "city": "Ahmedabad"},
            "just understand requirements": {"goal": "understand_requirements"},
        }
    )
    start_conversation(case_file)
    result = handle_turn(case_file, "Gujarat, Ahmedabad", llm)
    case_file = result.case_file

    result = handle_turn(case_file, "just understand requirements", llm)

    assert "upload your existing NOC" not in result.agent_message


def test_small_residential_building_skips_egress_and_systems_questions():
    """Node 3a: once height_m/built_up_area_sqm put a Residential building
    within Table 7A's self-certification threshold (area<=500 sqm,
    height<=24 m), the egress and existing_systems questions should be
    skipped entirely and the flow should jump straight to confirmation.
    """
    case_file = make_case_file()
    llm = ScriptedLLMClient(
        extractions={
            "Gujarat, Ahmedabad": {"state": "Gujarat", "city": "Ahmedabad"},
            "just understand requirements": {"goal": "understand_requirements"},
            "Residential": {"occupancy_type": "Residential"},
            "apartment house": {"occupancy_subdivision": "A-III"},
            "10 meters, 3 floors, no basement": {
                "height_m": 10,
                "floors_above_ground": 3,
                "floors_below_ground": 0,
            },
            "400 sqm": {"built_up_area_sqm": 400},
        }
    )
    start_conversation(case_file)

    turns = [
        "Gujarat, Ahmedabad",
        "just understand requirements",
        "Residential",
        "apartment house",
        "10 meters, 3 floors, no basement",
    ]
    result = None
    for turn in turns:
        result = handle_turn(case_file, turn, llm)
        case_file = result.case_file

    # Still pending "area" - egress/existing_systems shouldn't matter yet.
    assert "built-up area" in result.agent_message

    result = handle_turn(case_file, "400 sqm", llm)
    case_file = result.case_file

    assert "self-certification" in result.agent_message
    assert case_file.conversation_stage == ConversationStage.CONFIRMING
    assert "number_of_staircases" not in case_file.field_sources
    assert "existing_fire_systems" not in case_file.field_sources


def test_larger_residential_building_still_asks_egress_and_systems():
    case_file = make_case_file()
    llm = ScriptedLLMClient(
        extractions={
            "Gujarat, Ahmedabad": {"state": "Gujarat", "city": "Ahmedabad"},
            "just understand requirements": {"goal": "understand_requirements"},
            "Residential": {"occupancy_type": "Residential"},
            "apartment house": {"occupancy_subdivision": "A-III"},
            "40 meters, 12 floors, no basement": {
                "height_m": 40,
                "floors_above_ground": 12,
                "floors_below_ground": 0,
            },
            "5000 sqm": {"built_up_area_sqm": 5000},
        }
    )
    start_conversation(case_file)

    turns = [
        "Gujarat, Ahmedabad",
        "just understand requirements",
        "Residential",
        "apartment house",
        "40 meters, 12 floors, no basement",
        "5000 sqm",
    ]
    result = None
    for turn in turns:
        result = handle_turn(case_file, turn, llm)
        case_file = result.case_file

    assert "self-certification" not in result.agent_message
    assert "staircases" in result.agent_message
    assert case_file.conversation_stage == ConversationStage.INTAKE


def test_mixed_use_intake_collects_breakdown_and_classifies():
    """Node 3b: a Mixed Use occupancy answer should trigger the
    occupancy_breakdown node (skipping hazard_band/subdivision, since neither
    applies at the top level for this combination), and the resulting Case
    File should classify via classify_mixed_use() - see
    test_classifier_mixed_use.py for the engine-level assertions this reuses
    (Storage 600 sqm -> HL-5, Mercantile 1200 sqm subdivision F -> CL-4).
    """
    case_file = make_case_file()
    from app.models.case_file import OccupancyBreakdownItem, OccupancyType

    llm = ScriptedLLMClient(
        extractions={
            "Gujarat, Ahmedabad": {"state": "Gujarat", "city": "Ahmedabad"},
            "just understand requirements": {"goal": "understand_requirements"},
            "Mixed Use": {"occupancy_type": "Mixed Use"},
            "ground floor retail, 1200 sqm; floors 1-5 storage, 600 sqm": {
                "occupancy_breakdown": [
                    OccupancyBreakdownItem(
                        type=OccupancyType.MERCANTILE,
                        floor_range="G",
                        floor_area_sqm=1200,
                        subdivision="F",
                    ),
                    OccupancyBreakdownItem(
                        type=OccupancyType.STORAGE, floor_range="1-5", floor_area_sqm=600
                    ),
                ]
            },
            "9.5 meters, 1 floor, no basement": {
                "height_m": 9.5,
                "floors_above_ground": 1,
                "floors_below_ground": 0,
            },
            "1800 sqm total": {"built_up_area_sqm": 1800},
            "2 staircases, 4 exits": {"number_of_staircases": 2, "number_of_exits": 4},
            "none yet": {"existing_fire_systems": []},
            "yes that's right": {},
        }
    )

    start = start_conversation(case_file)
    case_file = start.case_file

    turns = [
        "Gujarat, Ahmedabad",
        "just understand requirements",
        "Mixed Use",
        "ground floor retail, 1200 sqm; floors 1-5 storage, 600 sqm",
        "9.5 meters, 1 floor, no basement",
        "1800 sqm total",
        "2 staircases, 4 exits",
        "none yet",
    ]
    result = None
    for turn in turns:
        result = handle_turn(case_file, turn, llm)
        case_file = result.case_file

    assert case_file.conversation_stage == ConversationStage.CONFIRMING
    assert "Mercantile" in result.agent_message
    assert "Storage" in result.agent_message

    result = handle_turn(case_file, "yes that's right", llm)
    case_file = result.case_file

    assert case_file.conversation_stage == ConversationStage.CLASSIFIED
    assert case_file.classification_result.require_human_review_flag is False
    assert "HL-5" in " ".join(case_file.classification_result.applicable_clauses)
    assert "CL-4" in " ".join(case_file.classification_result.applicable_clauses)


def test_knowledge_qa_side_branch_returns_to_pending_question():
    case_file = make_case_file()
    start_conversation(case_file)  # pending node is now "location"

    llm = ScriptedLLMClient(
        extractions={},
        intents={"what's a refuge area?": "question"},
    )
    result = handle_turn(case_file, "what's a refuge area?", llm)

    assert "[answer to: what's a refuge area?]" in result.agent_message
    assert "Back to:" in result.agent_message
    # Case file untouched - still nothing filled, still on the location node.
    assert "state" not in result.case_file.field_sources

    calls = llm.calls
    assert "classify_intent:what's a refuge area?" in calls
    assert "answer_question:what's a refuge area?" in calls
    assert not any(c.startswith("extract_fields") for c in calls)


def test_unparseable_answer_reasks_same_question_without_advancing():
    case_file = make_case_file()
    start_conversation(case_file)

    llm = ScriptedLLMClient(extractions={})  # extract_fields returns {} for everything
    result = handle_turn(case_file, "uh i dunno", llm)

    assert "didn't catch that" in result.agent_message
    assert "state" not in result.case_file.field_sources


class UnconfiguredLLMClient:
    """Every method raises LLMNotConfiguredError, like a real LLMClient with
    no API key set - used to prove handle_turn fails open everywhere it
    calls the LLM, not just at the call sites earlier tests happened to
    cover. Regression coverage for a bug a live browser test caught: the
    Knowledge Q&A call sites (both the mid-intake side-branch and the
    post-classification free-chat branch) weren't wrapped, so this exact
    scenario raised an uncaught 500 instead of a graceful reply.
    """

    def classify_intent(self, user_text, pending_question):
        raise LLMNotConfiguredError("no key")

    def extract_fields(self, user_text, field_types, context=""):
        raise LLMNotConfiguredError("no key")

    def answer_question(self, question, knowledge_context, model_tier="reasoning"):
        raise LLMNotConfiguredError("no key")


def test_qa_side_branch_fails_open_when_llm_not_configured():
    case_file = make_case_file()
    start_conversation(case_file)

    # classify_intent raising falls back to "answer" (existing behavior),
    # so this exercises extract_fields's fail-open path, not answer_question's -
    # see the CLASSIFIED-stage test below for that one.
    result = handle_turn(case_file, "some message", UnconfiguredLLMClient())

    assert "didn't catch that" in result.agent_message


def test_classified_stage_qa_fails_open_when_llm_not_configured():
    case_file = make_case_file()
    case_file.conversation_stage = ConversationStage.CLASSIFIED

    result = handle_turn(case_file, "what's a refuge area?", UnconfiguredLLMClient())

    assert "no LLM provider is configured" in result.agent_message
    assert result.case_file.conversation_stage == ConversationStage.CLASSIFIED
