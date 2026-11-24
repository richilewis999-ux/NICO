from database import save_memory, load_memory
from ollama_client import build_messages
from state_machine import StateMachine


def test_memory_round_trip(tmp_path, monkeypatch):
    import database
    from config import MEMORY_FILE

    test_file = tmp_path / "memory.json"
    monkeypatch.setattr(database, "MEMORY_FILE", test_file)

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]

    assert database.save_memory(messages)
    assert database.load_memory() == messages


def test_simple_greeting_uses_short_history():
    messages, num_predict = build_messages(
        [{"role": "user", "content": "old"}],
        "hello",
    )

    assert len(messages) <= 4
    assert num_predict == 100


def test_complex_request_has_system_and_history():
    messages, num_predict = build_messages(
        [
            {"role": "user", "content": "Explain Python"},
            {"role": "assistant", "content": "Okay"},
        ],
        "Explain the difference between sync and async",
    )

    assert messages[0]["role"] == "system"
    assert messages[-1]["content"].startswith("Explain")
    assert num_predict == 200


def test_state_machine_rejects_invalid_state():
    machine = StateMachine()
    machine.set("INVALID")

    assert machine.get() == "STANDBY"