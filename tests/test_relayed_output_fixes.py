"""Two defects found in DeepSeek run a1098ee7 (2026-11-11) by a separate output review."""
from tradingagents.agents.document_questions import parse_document_questions
from tradingagents.agents.evidence_presentation import PORTFOLIO_WITHHELD, without_portfolio_figures


def test_position_figures_in_plain_portfolio_words_are_withheld():
    for leaked in ("It justifies Underweight given the extreme 35.8% portfolio concentration.",
                   "Reduce DOCN toward the Underweight target of 2.5%.",
                   "Move to the Overweight target of 7.5% over time.",
                   "The file shows approximately 1,402 units, reducing roughly 1,304 units.",
                   "A 35.8% concentration is too high."):
        assert PORTFOLIO_WITHHELD in without_portfolio_figures(leaked), leaked
    # Evidence and case weights are not position figures.
    for kept in ("Retain the prior subjective 50% weight: the 6x multiple is plausible.",
                 "Customers above 100,000 USD are 41% of revenue, a concentration risk.",
                 "The vendor price target of 100 USD is unverified.", "The company added 1,402 new customers."):
        assert without_portfolio_figures(kept) == kept, kept


def _fence(body):
    return f"Closing argument.\n\n```document_questions\n{body}\n```"


def test_a_question_list_with_a_broken_bracket_keeps_its_well_formed_questions():
    """The bull's list lost its opening bracket; the whole side was dropped and only the bear was looked up."""
    broken = ('["transcript: 2027 revenue growth 60 percent bookings pipeline RPO"],\n'
              '{"query": "2027 formal revenue guidance digitalocean", "scope": "post_filing_event"}\n]')
    parsed = parse_document_questions(_fence(broken), "bull")
    assert parsed["status"] == "ready"
    assert parsed["questions"] == [
        {"question_id": "bull-1", "query": "transcript: 2027 revenue growth 60 percent bookings pipeline RPO"},
        {"question_id": "bull-2", "query": "2027 formal revenue guidance digitalocean", "scope": "post_filing_event"}]
    assert parsed["rejected"] == ["Repaired: the list was not valid JSON; 2 well-formed questions were recovered from it."]
    trailing = parse_document_questions(_fence('["lease commencement schedule", "note settlement",'), "bear")
    assert [q["query"] for q in trailing["questions"]] == ["lease commencement schedule", "note settlement"]


def test_a_list_with_nothing_usable_is_still_rejected_and_a_valid_list_is_untouched():
    for hopeless in ("no questions here", '{"q": "lease"}', "[[[", '{"query": 5}'):
        parsed = parse_document_questions(_fence(hopeless), "bull")
        assert parsed["status"] == "malformed" and parsed["questions"] == []
    good = parse_document_questions(_fence('["lease commencement schedule"]'), "bull")
    assert good["status"] == "ready" and good["rejected"] == []
