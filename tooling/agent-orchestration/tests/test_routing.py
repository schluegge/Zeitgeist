from zeitgeist_orchestration.routing import route_tool


def test_current_gpui_docs_use_grounded_docs() -> None:
    assert route_tool("What does the current GPUI documentation say about X?") == "grounded_docs"


def test_callers_use_code_review_graph() -> None:
    assert route_tool("What calls this function?") == "code_review_graph"


def test_exact_rust_symbol_definition_uses_lsp() -> None:
    question = "Where is this exact Rust symbol defined?"
    assert route_tool(question) == "rust_analyzer"


def test_taint_reachability_uses_code_graph_rag() -> None:
    question = "Can this user-controlled input reach this database operation?"
    assert route_tool(question) == "code_graph_rag"


def test_exact_rust_type_uses_lsp() -> None:
    assert route_tool("What is the exact type of this Rust symbol?") == "rust_analyzer"
