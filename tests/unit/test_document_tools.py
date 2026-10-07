import pytest
import os
from pathlib import Path
from foundation.event_bus.event_bus import EventBus
from action.action_executor.action_executor import ActionExecutor
from core_ai.tool_calling.definitions import get_tool_definition


@pytest.fixture
def action_executor():
    bus = EventBus()
    return ActionExecutor(bus)


import shutil

@pytest.fixture
def temp_doc_dir():
    d = Path(__file__).parent.parent.parent / "data" / "test_tmp" / "docs"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    try:
        shutil.rmtree(d.parent, ignore_errors=True)
    except Exception:
        pass


def test_document_tools_require_permission():
    """Verify read_document, edit_docx, and generate_pdf all require explicit user permission."""
    for tool_name in ["read_document", "edit_docx", "generate_pdf"]:
        tool_def = get_tool_definition(tool_name)
        assert tool_def is not None, f"Tool {tool_name} must be defined"
        assert tool_def.requires_permission is True, f"Tool {tool_name} must require permission"
        assert tool_def.category == "file"


def test_docx_create_and_read(action_executor, temp_doc_dir):
    """Test creating a new docx and reading back its contents."""
    doc_path = str(temp_doc_dir / "test_report.docx")
    
    # 1. Create
    res = action_executor._edit_docx(
        target=doc_path,
        params={
            "action": "create",
            "title": "Quarterly Performance",
            "content": "Paragraph one: All metrics are exceeding expectations.\n\nParagraph two: Revenue grew by 25%."
        }
    )
    assert res["status"] == "success"
    assert res["action"] == "create"
    assert Path(doc_path).exists()

    # 2. Read back
    read_res = action_executor._read_document(
        target=doc_path,
        params={}
    )
    assert read_res["status"] == "success"
    assert read_res["format"] == "docx"
    assert "Quarterly Performance" in read_res["content"]
    assert "Revenue grew by 25%" in read_res["content"]
    assert read_res["paragraph_count"] >= 3


def test_docx_append_and_replace(action_executor, temp_doc_dir):
    """Test appending content and replacing text in an existing docx."""
    doc_path = str(temp_doc_dir / "notes.docx")

    # 1. Create base
    action_executor._edit_docx(
        target=doc_path,
        params={
            "action": "create",
            "title": "Meeting Notes",
            "content": "Status: Pending Review."
        }
    )

    # 2. Append section
    append_res = action_executor._edit_docx(
        target=doc_path,
        params={
            "action": "append",
            "title": "Action Items",
            "content": "Assigned to Alice for final approval."
        }
    )
    assert append_res["status"] == "success"
    assert append_res["action"] == "append"

    # 3. Replace text
    replace_res = action_executor._edit_docx(
        target=doc_path,
        params={
            "action": "replace_text",
            "search_text": "Pending Review",
            "replace_text": "Approved by Management"
        }
    )
    assert replace_res["status"] == "success"
    assert replace_res["replacements_made"] >= 1

    # 4. Verify modified content
    read_res = action_executor._read_document(target=doc_path, params={})
    assert "Approved by Management" in read_res["content"]
    assert "Pending Review" not in read_res["content"]
    assert "Action Items" in read_res["content"]


def test_generate_pdf_and_read(action_executor, temp_doc_dir):
    """Test generating a PDF and reading text from it."""
    pdf_path = str(temp_doc_dir / "summary.pdf")

    # 1. Generate PDF
    gen_res = action_executor._generate_pdf(
        target=pdf_path,
        params={
            "title": "HELIX Executive Summary",
            "content": "HELIX is an advanced AI system with secure tool calling.\n\nAll sensitive actions require user approval."
        }
    )
    assert gen_res["status"] == "success"
    assert gen_res["size_bytes"] > 0
    assert Path(pdf_path).exists()

    # 2. Read back PDF
    read_res = action_executor._read_document(target=pdf_path, params={})
    assert read_res["status"] == "success"
    assert read_res["format"] == "pdf"
    assert read_res["total_pages"] >= 1
    assert "HELIX Executive Summary" in read_res["content"]
    assert "All sensitive actions require user approval" in read_res["content"]


def test_security_blocked_paths(action_executor):
    """Test that blocked system directories raise PermissionError."""
    blocked_path = "C:\\Windows\\System32\\test_doc.docx"
    with pytest.raises(PermissionError):
        action_executor._read_document(target=blocked_path, params={})

    with pytest.raises(PermissionError):
        action_executor._edit_docx(target=blocked_path, params={"action": "create", "content": "blocked"})

    with pytest.raises(PermissionError):
        action_executor._generate_pdf(target=blocked_path, params={"title": "blocked", "content": "blocked"})
