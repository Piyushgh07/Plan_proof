
"""Extract deterministic facts from PostgreSQL execution plans."""

from typing import Any


SCAN_NODE_TYPES = {
    "Index Only Scan": "index_only_scan",
    "Index Scan": "index_scan",
    "Bitmap Heap Scan": "bitmap_heap_scan",
    "Bitmap Index Scan": "bitmap_index_scan",
    "Seq Scan": "sequential_scan",
    "Parallel Seq Scan": "sequential_scan",
    "Tid Scan": "tid_scan",
    "Foreign Scan": "foreign_scan",
}


def collect_plan_nodes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all plan nodes in depth-first order."""
    nodes: list[dict[str, Any]] = []

    def visit(node: dict[str, Any]) -> None:
        nodes.append(node)

        children = node.get("Plans", [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    visit(child)

    visit(plan)
    return nodes


def classify_plan(plan: dict[str, Any]) -> str:
    """Classify the root node without confusing it with child scans."""
    root_type = plan.get("Node Type")

    if root_type in SCAN_NODE_TYPES:
        return SCAN_NODE_TYPES[root_type]

    return "other"


def summarize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Summarize root node, scan nodes, costs, rows, and index names."""
    nodes = collect_plan_nodes(plan)

    scan_nodes = [
        {
            "node_type": node.get("Node Type"),
            "strategy": SCAN_NODE_TYPES[node["Node Type"]],
            "index_name": node.get("Index Name"),
            "estimated_cost": node.get("Total Cost"),
            "estimated_rows": node.get("Plan Rows"),
        }
        for node in nodes
        if node.get("Node Type") in SCAN_NODE_TYPES
    ]

    return {
        "root_node": plan.get("Node Type"),
        "root_strategy": classify_plan(plan),
        "scan_strategies": sorted({
            scan["strategy"] for scan in scan_nodes
        }),
        "scan_nodes": scan_nodes,
        "total_cost": plan.get("Total Cost"),
        "estimated_rows": plan.get("Plan Rows"),
        "index_names": sorted({
            node["Index Name"]
            for node in nodes
            if isinstance(node.get("Index Name"), str)
        }),
    }
