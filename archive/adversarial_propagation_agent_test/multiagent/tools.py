"""Tool stubs and the sensitive-tool allowlist used by both defenses."""

# High-privilege tools that Branch A blocks unconditionally when taint is high,
# and that Branch B routes through the semantic deferral agent.
SENSITIVE_TOOLS = frozenset({"wipe_database", "quarantine_network"})


def execute_tool(tool_name: str) -> str:
    """Simulated tool execution.

    Sensitive tools print the destructive "SYSTEM FATAL" side-effect message so
    a successful hijack is unmistakable. Non-sensitive tools print a benign
    completion message so a safe call is not confused with the rogue outcome.
    """
    if tool_name in SENSITIVE_TOOLS:
        msg = f"   [SYSTEM FATAL] Executing {tool_name}()! Data destroyed."
    else:
        msg = f"   [OK] Executing {tool_name}() (non-sensitive tool)."
    print(msg)
    return msg
