VALID_STATES = (
    "STANDBY",
    "LISTENING",
    "PROCESSING",
    "RESPONDING",
    "SYSTEM ERROR",
)


class StateMachine:
    """Validate and store the application's current UI state."""

    def __init__(self, initial="STANDBY"):
        self._state = "STANDBY"
        self.set(initial)

    def set(self, state):
        if state not in VALID_STATES:
            state = "STANDBY"
        self._state = state

    def get(self):
        return self._state

    def is_valid(self, state):
        return state in VALID_STATES
