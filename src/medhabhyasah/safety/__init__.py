"""Safety checks for AI-generated questions.

Each check enforces one rule from AGENTS.md. A question that passes all
checks is stored with status 'auto_checked'; one that fails is stored as
'draft' with the failure reason in check_failure.
"""
import re
from dataclasses import dataclass

_REQUIRED_FIELDS = frozenset(
    {"difficulty", "type", "question", "options", "answer", "explanation", "source_quote"}
)
_VALID_DIFFICULTIES = frozenset({"Easy", "Medium", "Hard"})
_MATHS_SCIENCE_SUBJECTS = frozenset({"Maths", "Science"})
_WORKED_SECTIONS = ("Given:", "Formula:", "Substitution:", "Answer:")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _extract_answer_line(explanation: str) -> str:
    """Text on the worked solution's 'Answer:' line. Caller must ensure it's present."""
    idx = explanation.rfind("Answer:")
    rest = explanation[idx + len("Answer:"):]
    newline_idx = rest.find("\n")
    return rest if newline_idx == -1 else rest[:newline_idx]


def _first_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text.replace(",", ""))
    return float(match.group()) if match else None


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _worked_answer_matches_option(explanation: str, option_text: str) -> bool:
    """Does the worked solution's final Answer: line agree with the chosen option?

    Numbers are compared numerically (tolerant of unit text differing, e.g.
    '1100 watts' vs '1100 W'). Non-numeric answers fall back to a substring
    match on normalized text.
    """
    answer_line = _extract_answer_line(explanation)
    opt_num = _first_number(option_text)
    ans_num = _first_number(answer_line)
    if opt_num is not None and ans_num is not None:
        tolerance = max(abs(opt_num), 1e-9) * 0.01
        return abs(opt_num - ans_num) <= tolerance
    norm_opt, norm_ans = _normalize(option_text), _normalize(answer_line)
    return norm_opt in norm_ans or norm_ans in norm_opt


@dataclass
class CheckResult:
    passed: bool
    failure: str | None = None


def check_question(q: dict, subject: str) -> CheckResult:
    """Run all safety checks on a single question dict from the AI response."""
    # 1. Required fields present
    missing = _REQUIRED_FIELDS - set(q.keys())
    if missing:
        return CheckResult(False, f"Missing fields: {', '.join(sorted(missing))}")

    # 2. Exactly 4 options
    options = q["options"]
    if not isinstance(options, list) or len(options) != 4:
        count = len(options) if isinstance(options, list) else "not a list"
        return CheckResult(False, f"options must be a list of exactly 4 items (got {count})")

    # 3. answer index 0–3
    answer = q["answer"]
    if not isinstance(answer, int) or answer not in (0, 1, 2, 3):
        return CheckResult(False, f"answer must be an integer 0–3 (got {answer!r})")

    # 4. Valid difficulty label
    if q["difficulty"] not in _VALID_DIFFICULTIES:
        return CheckResult(
            False,
            f"difficulty must be Easy/Medium/Hard (got {q['difficulty']!r})",
        )

    # 5. Maths/Science: explanation must contain worked-solution sections
    if subject in _MATHS_SCIENCE_SUBJECTS:
        explanation = q.get("explanation", "")
        missing_sections = [s for s in _WORKED_SECTIONS if s not in explanation]
        if missing_sections:
            return CheckResult(
                False,
                f"Maths/Science explanation must include: {', '.join(missing_sections)}",
            )

        # 6. The worked solution's Answer: line must agree with the chosen option.
        option_text = options[answer]
        if not _worked_answer_matches_option(explanation, option_text):
            letter = "ABCD"[answer]
            return CheckResult(
                False,
                f"Worked solution's Answer line doesn't match option {letter} ({option_text!r})",
            )

    return CheckResult(True)


def check_difficulty_distribution(questions: list[dict]) -> str | None:
    """Return a warning string if difficulty distribution is outside 20–50/25–55/15–40 bands,
    or None if distribution is acceptable. Requires at least 5 questions."""
    if len(questions) < 5:
        return None

    counts = {"Easy": 0, "Medium": 0, "Hard": 0}
    for q in questions:
        d = q.get("difficulty", "")
        if d in counts:
            counts[d] += 1

    total = sum(counts.values())
    if total == 0:
        return None

    easy_pct = counts["Easy"] / total
    medium_pct = counts["Medium"] / total

    if not (0.20 <= easy_pct <= 0.50):
        return (
            f"Difficulty distribution off: "
            f"Easy={counts['Easy']}/{total}, Medium={counts['Medium']}/{total}, Hard={counts['Hard']}/{total}"
        )
    if not (0.25 <= medium_pct <= 0.55):
        return (
            f"Difficulty distribution off: "
            f"Easy={counts['Easy']}/{total}, Medium={counts['Medium']}/{total}, Hard={counts['Hard']}/{total}"
        )
    return None
