"""LangGraph-shaped fixture for state-key read/write extraction tests."""


def node_read(state):
    return state["read_key"]


def node_get(state):
    # Read via .get() — must be captured (the interrupt_state gotcha).
    x = state.get("interrupt_state")
    return x


def node_write(state):
    state["retry_reason"] = "failure"
    return state


def node_nested(state):
    # Nested subscript: leaf key must be captured.
    return state["payload"]["retry_reason"]


def node_dynamic(state, idx):
    # Dynamic intermediate key tolerated; literal leaf still captured.
    return state[idx]["dynamic_ok"]


def node_pop(state):
    return state.pop("popped")


def node_setdefault(state):
    state.setdefault("seeded", [])


def node_aug(state):
    state["counter"] += 1


def write_interrupt_a(state):
    state["interrupt_state"] = "a"


def write_interrupt_b(state):
    state["interrupt_state"] = "b"


def write_interrupt_c(state):
    state["interrupt_state"] = "c"


def write_interrupt_d(state):
    state["interrupt_state"] = "d"


def write_interrupt_e(state):
    state["interrupt_state"] = "e"


def not_the_state(cfg):
    # A dict that is NOT the configured receiver — must emit no state edges.
    return cfg["unrelated"]


def node_nested_write(state):
    # Nested WRITE: navigating "payload" is a READ; only the leaf is a WRITE.
    state["payload"]["retry_reason"] = "boom"


def node_for_target(state, items):
    # Loop assignment target -> WRITES "cursor".
    for state["cursor"] in items:
        pass


def node_del(state):
    # Deletion is a mutation -> WRITES "stale".
    del state["stale"]


def node_aug_rhs(state, total):
    # state on the RHS of an augmented assignment is a pure READ of "delta".
    total += state["delta"]
    return total


def node_escaped_key(state):
    # "\x72\x65\x61\x64_key" decodes to the same key as node_read's "read_key".
    return state["\x72\x65\x61\x64_key"]
