from app.services.token_budget import BudgetExceededError, token_budget_guard


def test_token_budget_warns_before_hard_limit_and_then_blocks():
    budget = token_budget_guard.allocate(session_id="s1", user_id="u1", complexity="simple")

    warning_text = "a" * 14000  # ~= 3500 tokens
    consumed, warned = token_budget_guard.consume_input(budget, warning_text)

    assert consumed > 0
    assert warned is True
    assert budget.consumed > 0
    assert budget.remaining < budget.total_budget

    blocked = False
    try:
        token_budget_guard.consume_output(budget, "b" * 5000)  # ~= 1250 tokens
    except BudgetExceededError:
        blocked = True

    assert blocked is True
