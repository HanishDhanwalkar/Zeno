from zeno_ai.tokens import count_tokens, count_message_tokens


def test_count_tokens_empty():
    assert count_tokens("") == 0
    assert count_tokens(None) == 0


def test_count_tokens_nonempty_is_positive():
    assert count_tokens("hello world") >= 2


def test_count_tokens_scales_with_length():
    short = count_tokens("a b c")
    long = count_tokens("a b c d e f g h i j k l")
    assert long > short


def test_count_message_tokens_includes_overhead_and_content():
    msgs = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hello there friend"},
    ]
    total = count_message_tokens(msgs)
    assert total > count_tokens("you are helpful") + count_tokens("hello there friend")


def test_count_message_tokens_counts_tool_calls():
    msgs = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "read", "arguments": '{"path":"a.txt"}'}}
            ],
        }
    ]
    assert count_message_tokens(msgs) > 4
