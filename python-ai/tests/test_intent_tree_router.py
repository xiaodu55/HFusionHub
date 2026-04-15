from app.core.rag.intent_tree_router import resolve_intent_route


def _candidate(name, kb_id, description="", top_k=5):
    return {
        "intent_code": name.lower(),
        "name": name,
        "description": description,
        "kind": "KB",
        "knowledge_base_id": kb_id,
        "top_k": top_k,
        "path": f"技术/{name}",
    }


def test_explicit_knowledge_base_wins():
    decision = resolve_intent_route("虚拟线程", [_candidate("Java", 2)], 9)
    assert decision["status"] == "explicit"
    assert decision["knowledge_base_id"] == 9


def test_greeting_does_not_route_to_knowledge_base():
    decision = resolve_intent_route("你好", [_candidate("问候语", 2, "你好 您好")])
    assert decision["status"] == "chitchat"
    assert decision["knowledge_base_id"] is None


def test_routes_matching_topic_and_preserves_top_k():
    decision = resolve_intent_route(
        "什么是 Java 虚拟线程",
        [_candidate("Java", 2, "Java 虚拟线程 并发", top_k=8)],
    )
    assert decision["status"] == "matched"
    assert decision["knowledge_base_id"] == 2
    assert decision["top_k"] == 8


def test_close_different_knowledge_bases_require_clarification():
    decision = resolve_intent_route(
        "退款流程",
        [
            _candidate("退款流程", 2, "支付退款流程"),
            _candidate("退款流程", 3, "订单退款流程"),
        ],
    )
    assert decision["status"] == "ambiguous"
    assert len(decision["candidates"]) == 2
