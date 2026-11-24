
from unittest.mock import patch

from bugpilot.workflow import (
    investigate,
    fix,
    review,
    llm_review,
    route_llm_review,
    prepare_approval,
    GRAPH
)


ORIGINAL = """
def average(values):
    total = sum(values)
    return total / len(values)
"""

PATCHED = """
def average(values):
    total = sum(values)
    return total / len(values) if values else 0.0
"""

TRACEBACK = """
Traceback (most recent call last):
  File "/app/app.py", line 4, in average
ZeroDivisionError: division by zero
"""


def test_investigator():

    result = investigate({
        "traceback": TRACEBACK,
        "steps": []
    })

    assert result["filename"] == "app.py"
    assert result["error_type"] == "ZeroDivisionError"


@patch("bugpilot.workflow.ask_llm")
def test_llm_fixer(mock_llm):

    mock_llm.return_value = {
        "patched_code": PATCHED,
        "explanation": "Handle empty input"
    }

    result = fix({
        "error_type": "ZeroDivisionError",
        "source": ORIGINAL,
        "steps": []
    })

    assert "if values else 0.0" in result["patched"]
    assert result["attempts"] == 1
    assert result["diff"]


def test_static_review_passes():

    result = review({
        "patched": PATCHED,
        "diff": "example diff",
        "steps": []
    })

    assert result["review_passed"] is True


def test_static_review_rejects_invalid_python():

    result = review({
        "patched": "def broken(",
        "diff": "example diff",
        "steps": []
    })

    assert result["review_passed"] is False


@patch("bugpilot.workflow.ask_llm")
def test_llm_reviewer(mock_llm):

    mock_llm.return_value = {
        "approved": True,
        "feedback": "Patch addresses the root cause"
    }

    result = llm_review({
        "error_type": "ZeroDivisionError",
        "source": ORIGINAL,
        "patched": PATCHED,
        "diff": "example diff",
        "steps": []
    })

    assert result["review_passed"] is True


def test_retry_route(monkeypatch):

    monkeypatch.setenv("MAX_FIX_ATTEMPTS", "3")

    result = route_llm_review({
        "review_passed": False,
        "attempts": 1
    })

    assert result == "retry"


def test_retry_limit(monkeypatch):

    monkeypatch.setenv("MAX_FIX_ATTEMPTS", "3")

    result = route_llm_review({
        "review_passed": False,
        "attempts": 3
    })

    assert result == "failed"


def test_approval_required():

    result = prepare_approval({"steps": []})

    assert result["status"] == "awaiting_approval"


@patch("bugpilot.github.get_file")
@patch("bugpilot.workflow.ask_llm")
def test_complete_workflow(mock_llm, mock_github):

    mock_github.return_value = (
        ORIGINAL,
        "mock-github-sha"
    )

    mock_llm.side_effect = [
        {
            "root_cause": "Empty list causes division by zero",
            "affected_function": "average",
            "recommended_fix": "Handle empty list"
        },
        {
            "patched_code": PATCHED,
            "explanation": "Return zero for empty input"
        },
        {
            "approved": True,
            "feedback": "Patch is correct"
        }
    ]

    result = GRAPH.invoke({
        "traceback": TRACEBACK,
        "steps": []
    })

    assert result["status"] == "awaiting_approval"
    assert result["attempts"] == 1
    assert mock_llm.call_count == 3
    assert result["diff"]
