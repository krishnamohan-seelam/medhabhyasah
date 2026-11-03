"""Safety tests for AI-generated question validation rules (AGENTS.md).

Every safety rule added in safety/__init__.py must be covered here.
"""
import pytest

from medhabhyasah.safety import CheckResult, check_difficulty_distribution, check_question


# ── Base valid question ───────────────────────────────────────────────────────

def _base_q(**overrides):
    q = {
        "difficulty": "Easy",
        "type": "mcq",
        "question": "What is 2 + 2?",
        "options": ["1", "2", "4", "8"],
        "answer": 2,
        "explanation": "2 + 2 = 4.",
        "source_quote": "",
    }
    q.update(overrides)
    return q


def _maths_q(**overrides):
    q = {
        "difficulty": "Medium",
        "type": "mcq",
        "question": "A car travels 60 km in 1 hour. Find its speed.",
        "options": ["30 km/h", "60 km/h", "120 km/h", "15 km/h"],
        "answer": 1,
        "explanation": (
            "Given: distance = 60 km, time = 1 h\n"
            "Formula: speed = distance / time\n"
            "Substitution: speed = 60 / 1\n"
            "Answer: 60 km/h"
        ),
        "source_quote": "",
    }
    q.update(overrides)
    return q


# ── Rule 1: Required fields ───────────────────────────────────────────────────

def test_all_fields_present_passes():
    result = check_question(_base_q(), "English")
    assert result.passed is True
    assert result.failure is None


def test_missing_options_fails():
    q = _base_q()
    del q["options"]
    result = check_question(q, "Science")
    assert result.passed is False
    assert "options" in result.failure


def test_missing_answer_fails():
    q = _base_q()
    del q["answer"]
    result = check_question(q, "English")
    assert result.passed is False
    assert "answer" in result.failure


def test_missing_multiple_fields_fails():
    q = _base_q()
    del q["explanation"]
    del q["source_quote"]
    result = check_question(q, "Social Studies")
    assert result.passed is False
    assert "explanation" in result.failure or "source_quote" in result.failure


# ── Rule 2: Exactly 4 options ─────────────────────────────────────────────────

def test_three_options_fails():
    result = check_question(_base_q(options=["A", "B", "C"]), "English")
    assert result.passed is False
    assert "4" in result.failure


def test_five_options_fails():
    result = check_question(_base_q(options=["A", "B", "C", "D", "E"]), "English")
    assert result.passed is False
    assert "4" in result.failure


def test_options_not_a_list_fails():
    result = check_question(_base_q(options="ABCD"), "English")
    assert result.passed is False


def test_exactly_four_options_passes():
    result = check_question(_base_q(options=["A", "B", "C", "D"]), "English")
    assert result.passed is True


# ── Rule 3: answer index 0–3 ─────────────────────────────────────────────────

def test_answer_4_fails():
    result = check_question(_base_q(answer=4), "English")
    assert result.passed is False
    assert "0" in result.failure or "3" in result.failure


def test_answer_negative_fails():
    result = check_question(_base_q(answer=-1), "English")
    assert result.passed is False


def test_answer_string_fails():
    result = check_question(_base_q(answer="2"), "English")
    assert result.passed is False


def test_answer_0_passes():
    result = check_question(_base_q(answer=0), "English")
    assert result.passed is True


def test_answer_3_passes():
    result = check_question(_base_q(answer=3), "English")
    assert result.passed is True


# ── Rule 4: Difficulty label ──────────────────────────────────────────────────

def test_valid_difficulties_pass():
    for d in ("Easy", "Medium", "Hard"):
        result = check_question(_base_q(difficulty=d), "English")
        assert result.passed is True, f"Expected pass for {d}"


def test_invalid_difficulty_fails():
    result = check_question(_base_q(difficulty="Very Easy"), "English")
    assert result.passed is False
    assert "Very Easy" in result.failure


def test_lowercase_difficulty_fails():
    result = check_question(_base_q(difficulty="easy"), "English")
    assert result.passed is False


# ── Rule 5: Maths/Science worked solution ────────────────────────────────────

def test_maths_with_worked_solution_passes():
    result = check_question(_maths_q(), "Maths")
    assert result.passed is True


def test_science_with_worked_solution_passes():
    result = check_question(_maths_q(), "Science")
    assert result.passed is True


def test_maths_without_given_fails():
    q = _maths_q(explanation="Formula: v=d/t\nSubstitution: 60/1\nAnswer: 60 km/h")
    result = check_question(q, "Maths")
    assert result.passed is False
    assert "Given:" in result.failure


def test_maths_without_formula_fails():
    q = _maths_q(explanation="Given: d=60km, t=1h\nSubstitution: 60/1\nAnswer: 60 km/h")
    result = check_question(q, "Maths")
    assert result.passed is False
    assert "Formula:" in result.failure


def test_maths_without_substitution_fails():
    q = _maths_q(explanation="Given: d=60km, t=1h\nFormula: v=d/t\nAnswer: 60 km/h")
    result = check_question(q, "Maths")
    assert result.passed is False
    assert "Substitution:" in result.failure


def test_maths_without_answer_line_fails():
    q = _maths_q(explanation="Given: d=60km, t=1h\nFormula: v=d/t\nSubstitution: 60/1")
    result = check_question(q, "Maths")
    assert result.passed is False
    assert "Answer:" in result.failure


def test_english_does_not_require_worked_solution():
    # English questions with no worked solution should pass
    result = check_question(_base_q(explanation="Because the sentence uses a gerund."), "English")
    assert result.passed is True


def test_social_studies_does_not_require_worked_solution():
    result = check_question(_base_q(explanation="The capital of India is New Delhi."), "Social Studies")
    assert result.passed is True


# ── Rule 6: Difficulty distribution ─────────────────────────────────────────

def test_good_distribution_returns_none():
    questions = (
        [_base_q(difficulty="Easy")] * 4
        + [_base_q(difficulty="Medium")] * 4
        + [_base_q(difficulty="Hard")] * 2
    )
    assert check_difficulty_distribution(questions) is None


def test_all_easy_triggers_warning():
    questions = [_base_q(difficulty="Easy")] * 10
    warning = check_difficulty_distribution(questions)
    assert warning is not None
    assert "Easy" in warning


def test_fewer_than_5_no_distribution_check():
    questions = [_base_q(difficulty="Easy")] * 4
    assert check_difficulty_distribution(questions) is None


# ── Rule 7: Student routes never import generation ───────────────────────────

def test_generation_not_imported_at_api_module_level():
    """The api module must not import generation at the top level."""
    import importlib
    import sys

    # Remove cached modules so we get a fresh import
    for mod in list(sys.modules.keys()):
        if "medhabhyasah" in mod:
            del sys.modules[mod]

    import medhabhyasah.api
    assert "medhabhyasah.generation" not in sys.modules, (
        "medhabhyasah.generation was imported at module level in api/__init__.py — "
        "student routes would have access to the generation module"
    )
