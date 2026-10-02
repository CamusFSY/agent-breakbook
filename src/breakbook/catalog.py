"""Case descriptions and narrowly scoped evidence links."""

CASES = {
    "lost-ack": {
        "title": "The write succeeded. The acknowledgement did not.",
        "summary": "A retry submits the same notification twice.",
        "task": "Submit notification 'Build finished' for operation 'build-42' exactly once.",
        "tool": "send_notification",
        "mitigation": "Reuse a stable operation ID; enforce atomic deduplication at the service.",
        "evidence": ["https://github.com/mit-hun-k/faultbench"],
        "provenance": (
            "Original simulation of a known distributed-systems failure; see related work."
        ),
    },
    "hung-tool": {
        "title": "One tool never returns.",
        "summary": "A missing application deadline lets the harness watchdog end the run.",
        "task": "Fetch the build status. If the tool times out, report timed_out honestly.",
        "tool": "fetch_status",
        "mitigation": "Put a deadline at the tool boundary and cancel the pending operation.",
        "evidence": ["https://github.com/modelcontextprotocol/python-sdk/issues/1401"],
        "provenance": "Issue-inspired simulation, not a claim that the installed SDK has this bug.",
    },
    "retry-storm": {
        "title": "A transient error becomes an unbounded retry loop.",
        "summary": "A permanently unavailable provider exhausts the harness budget.",
        "task": "Read the inventory. If it remains unavailable, report unavailable.",
        "tool": "read_inventory",
        "mitigation": "Enforce an attempt budget outside the model and return an explicit failure.",
        "evidence": ["https://github.com/DeepAgentLabs/agentic-chaos"],
        "provenance": "Original local simulation; related fault-injection work is credited.",
    },
}
