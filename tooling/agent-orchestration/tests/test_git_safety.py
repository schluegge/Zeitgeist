from zeitgeist_orchestration.git_safety import validate_git_effect


def test_glass_push_is_blocked() -> None:
    result = validate_git_effect(remote="glass", expected_head="abc", actual_head="abc")
    assert not result.allowed
    assert result.reason == "protected upstream remote"


def test_zed_push_is_blocked() -> None:
    result = validate_git_effect(remote="zed", expected_head="abc", actual_head="abc")
    assert not result.allowed
    assert result.reason == "protected upstream remote"


def test_stale_head_blocks_origin_effect() -> None:
    result = validate_git_effect(remote="origin", expected_head="abc", actual_head="def")
    assert not result.allowed
    assert result.reason == "stale HEAD"


def test_origin_effect_is_allowed_when_head_matches() -> None:
    result = validate_git_effect(remote="origin", expected_head="abc", actual_head="abc")
    assert result.allowed
