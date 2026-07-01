"""Tool stubs and the sensitive-tool allowlist used by both defenses."""

# High-privilege tools that Branch A blocks unconditionally when taint is high,
# and that Branch B routes through the semantic deferral agent.
SENSITIVE_TOOLS = frozenset({"wipe_database", "quarantine_network"})


def execute_tool(tool_name: str) -> str:
    """Simulated tool execution.

    In the no-defense demo this prints the destructive side-effect message so
    the "rogue event" is visible. In the defended demos this function is
    reached only when the layered checks all pass.
    """
    msg = f"   [SYSTEM FATAL] Executing {tool_name}()! Data destroyed."
    print(msg)
    return msg
