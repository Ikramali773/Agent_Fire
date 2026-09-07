"""End-to-end intake conversation test using a scripted fake LLM - proves the
Node 1-7 -> confirm -> classify state machine (dialogue/manager.py) actually
completes and reaches the same deterministic classification the engine tests
verify elsewhere, without any real LLM call.
"""

import uuid

from app.dialogue.manager import handle_turn, start_conversation
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
