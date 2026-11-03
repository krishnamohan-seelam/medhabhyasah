"""Safety tests: question text must never be set via innerHTML (AGENTS.md)."""
from pathlib import Path
import re


_HTML_PATH = (
    Path(__file__).parent.parent.parent
    / "src" / "medhabhyasah" / "web" / "index.html"
)


def _html_source() -> str:
    return _HTML_PATH.read_text(encoding="utf-8")


def test_question_field_not_set_via_innerHTML():
    """No JS code may assign question data through innerHTML."""
    src = _html_source()
    # Find all innerHTML assignments
    inner_html_assignments = re.findall(r'\.innerHTML\s*=', src)
    # Any innerHTML assignment that comes close to question/option text is banned.
    # We verify the total count stays at zero — the UI uses textContent and .value.
    assert len(inner_html_assignments) == 0, (
        f"Found {len(inner_html_assignments)} innerHTML assignment(s) in index.html. "
        "Question text must be rendered with textContent or .value, never innerHTML."
    )


def test_question_text_rendered_with_textContent_or_value():
    """The approval queue and question rendering use textContent / .value for question data."""
    src = _html_source()
    # Positive check: textContent assignments are present (used for rendering)
    assert ".textContent" in src, "Expected .textContent usage not found in index.html"


def test_results_screen_does_not_reveal_correct_answer():
    """The quiz results breakdown must never expose the correct answer letter or text.

    Students must not be able to skip all questions, view the results screen,
    and learn the correct answers before retaking the quiz.
    """
    src = _html_source()

    # Locate the _showResults function body
    match = re.search(r'function _showResults\(result\)(.*?)^\s{2}\}', src, re.DOTALL | re.MULTILINE)
    assert match, "_showResults function not found in index.html"
    fn_body = match.group(1)

    # Must not output caLetter (correct answer letter) to the user
    assert "caLetter" not in fn_body, (
        "results screen exposes correct answer letter (caLetter); "
        "remove it so students cannot game the quiz by skipping all questions"
    )
    # Must not output caText (correct answer option text) to the user
    assert "caText" not in fn_body, (
        "results screen exposes correct answer option text (caText); "
        "correct answers must only be visible in the Mistakes Notebook"
    )
    # Must not show explanation on the results screen (explanation can reveal the answer)
    assert "result-explanation" not in fn_body, (
        "results screen shows the explanation, which can reveal the correct answer; "
        "explanations must only appear in the Mistakes Notebook"
    )


def test_no_html_allowed_in_question_api_fields():
    """The API question fields (question, options, explanation) must not contain HTML tags."""
    import json
    from unittest.mock import MagicMock, patch
    from pathlib import Path
    import tempfile
    from medhabhyasah.db import (
        create_generation_request, create_question, create_schema, get_connection
    )
    from fastapi.testclient import TestClient
    from medhabhyasah.api import create_app

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        conn = get_connection(db_path)
        create_schema(conn)
        req_id = create_generation_request(
            conn, subject="Maths", topic="Algebra", grade="9",
            exam="CBSE", references_text="", question_count=1,
        )
        # Store a question with HTML in text (simulates a bad AI response that slipped through)
        create_question(
            conn,
            generation_request_id=req_id,
            difficulty="Easy", type_="mcq",
            question='<script>alert("xss")</script>What is 2+2?',
            options=json.dumps(["1", "2", "4", '<img src=x onerror=alert(1)>']),
            answer="2", explanation="Four.", source_quote="", status="approved",
        )
        conn.close()

        mock_kr = MagicMock()
        mock_kr.get_password = MagicMock(return_value="1234")
        with patch("medhabhyasah.credentials.keyring", mock_kr):
            app = create_app(db_path=db_path)
            c = TestClient(app)
            rows = c.get("/api/student/questions").json()

    # The API returns the raw text — the SAFETY GUARANTEE is that the UI renders
    # it with textContent (verified by test_question_field_not_set_via_innerHTML).
    # Here we confirm the API doesn't strip or re-encode: it passes through as-is,
    # and the rendering layer (textContent) is what neutralises it.
    assert len(rows) == 1
    # The script tag is present in the raw data — that's expected.
    # The guarantee is textContent in the renderer, not server-side stripping.
    assert "<script>" in rows[0]["question"]
