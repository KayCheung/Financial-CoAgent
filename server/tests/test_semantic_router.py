from app.agent.router import semantic_router


def test_semantic_router_detects_invoice_ocr_requests():
    decision = semantic_router.route("请帮我识别这张发票并提取报销字段")

    assert decision.intent == "invoice_ocr"
    assert decision.confidence >= 0.55


def test_semantic_router_detects_knowledge_lookup_requests():
    decision = semantic_router.route("请检索制度文档后回答这条报销规则")

    assert decision.intent == "knowledge_qa"
    assert decision.confidence >= 0.55


def test_semantic_router_falls_back_to_general_chat():
    decision = semantic_router.route("帮我整理一个简洁的财务沟通回复")

    assert decision.intent == "general_chat"
    assert decision.confidence >= 0.35
