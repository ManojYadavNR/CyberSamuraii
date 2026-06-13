"""Rule-based investigation copilot — answers from live investigation data."""

from __future__ import annotations

from typing import Any


def _linked_accounts(result: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for cluster in result.get("correlation", {}).get("clusters", []):
        refs.extend(cluster.get("linked_account_refs", []))
        for acct in cluster.get("linked_accounts", []):
            ref = f"{acct.get('platform', 'unknown')}:{acct.get('handle', '')}"
            if ref not in refs:
                refs.append(ref)
    return refs


def _summarize_suspicious(result: dict[str, Any]) -> str:
    networks = result.get("graph", {}).get("suspicious_networks", [])
    if not networks:
        return "No suspicious networks flagged. Review correlation confidence and explainability for manual assessment."
    lines = []
    for net in networks[:5]:
        lines.append(
            f"• {net.get('network_type', 'unknown').replace('_', ' ').title()} "
            f"({net.get('confidence', 0) * 100:.0f}% confidence): "
            f"{'; '.join(net.get('indicators', [])[:2])}"
        )
    return "\n".join(lines)


def answer_copilot(message: str, context: dict[str, Any]) -> dict[str, Any]:
    msg = message.lower().strip()
    result = context.get("result", {})
    query = context.get("query", "")

    if any(k in msg for k in ("linked account", "linked accounts", "show accounts", "accounts")):
        accounts = _linked_accounts(result)
        if not accounts:
            return {
                "answer": "No linked accounts found yet. Run an investigation or check if tools returned results.",
                "data": {"accounts": []},
            }
        return {
            "answer": f"Found {len(accounts)} linked account(s):\n" + "\n".join(f"• {a}" for a in accounts[:30]),
            "data": {"accounts": accounts},
        }

    if any(k in msg for k in ("summarize", "summary", "suspect activity", "activity")):
        clusters = result.get("correlation", {}).get("clusters", [])
        fusion_score = result.get("fusion", {}).get("fusion_score", 0)
        tools_ok = result.get("tools_succeeded", 0)
        tools_fail = result.get("tools_failed", 0)
        answer = (
            f"Investigation summary for '{query}':\n"
            f"• Fusion confidence: {fusion_score * 100:.1f}%\n"
            f"• Identity clusters: {len(clusters)}\n"
            f"• Tools succeeded/failed: {tools_ok}/{tools_fail}\n"
            f"• Linked accounts: {len(_linked_accounts(result))}"
        )
        return {"answer": answer, "data": {"clusters": len(clusters)}}

    if any(k in msg for k in ("why suspicious", "why is this", "suspicious cluster", "why cluster")):
        explain = []
        for cluster in result.get("correlation", {}).get("clusters", []):
            explain.extend(cluster.get("explainability", [])[:5])
        suspicious = _summarize_suspicious(result)
        answer = "Explainability:\n" + ("\n".join(f"• {e}" for e in explain[:8]) if explain else "No explainability data.")
        answer += f"\n\nSuspicious network analysis:\n{suspicious}"
        return {"answer": answer, "data": {"explainability": explain}}

    if any(k in msg for k in ("evidence", "signals", "confidence")):
        lines = []
        for cluster in result.get("correlation", {}).get("clusters", [])[:3]:
            lines.append(f"Cluster {cluster.get('account_cluster_id')} — {cluster.get('confidence_score', 0):.1f}%")
            for ev in cluster.get("evidence", []):
                lines.append(f"  • {ev.get('type')}: {ev.get('score', 0):.2f} (weight {ev.get('weight', 0):.2f})")
        return {
            "answer": "\n".join(lines) if lines else "No evidence signals available.",
            "data": {"evidence_lines": lines},
        }

    if any(k in msg for k in ("graph", "network", "relationship")):
        graph = result.get("graph", {})
        return {
            "answer": (
                f"Graph: {graph.get('node_count', 0)} nodes, {graph.get('edge_count', 0)} edges. "
                f"Communities: {len(graph.get('clusters', []))}. "
                f"Suspicious networks: {len(graph.get('suspicious_networks', []))}."
            ),
            "data": graph,
        }

    return {
        "answer": (
            "I can help with:\n"
            "• 'show linked accounts'\n"
            "• 'summarize suspect activity'\n"
            "• 'why is this cluster suspicious?'\n"
            "• 'show evidence breakdown'\n"
            "• 'show graph summary'"
        ),
        "data": {},
    }
