import pytest

from agentkit import Agent, NullTracer
from browser_concepts_demo import FakeBrowser, make_browser_tools, offline_llm


def test_snapshot_has_refs_and_roles():
    snap = FakeBrowser().snapshot()
    assert '[e2] textbox "Search products"' in snap and '[e3] button "Search"' in snap


def test_stale_ref_gives_actionable_error():
    with pytest.raises(ValueError, match="new snapshot"):
        FakeBrowser().click("e7")  # Add-to-cart button product page pe hai, home pe nahi


def test_typing_into_a_button_is_rejected():
    with pytest.raises(ValueError, match="not a textbox"):
        FakeBrowser().type_text("e3", "x")


def test_agent_completes_shopping_goal_offline():
    b = FakeBrowser()
    res = Agent(offline_llm(), make_browser_tools(b), tracer=NullTracer()).run("buy cheapest keyboard")
    assert b.cart == ["Mechanical Keyboard K2 - ₹4,999"]
    assert "4,999" in res.output
