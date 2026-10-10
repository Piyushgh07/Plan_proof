
from app.verifier.plan_analysis import classify_plan, summarize_plan


def test_classifies_bitmap_heap_scan():
    plan = {
        "Node Type": "Bitmap Heap Scan",
        "Total Cost": 5751.93,
        "Plan Rows": 34167,
        "Plans": [
            {
                "Node Type": "Bitmap Index Scan",
                "Index Name": "<13625>btree_users_country",
                "Total Cost": 620.3,
                "Plan Rows": 34167,
            }
        ],
    }

    assert classify_plan(plan) == "bitmap_heap_scan"


def test_classifies_index_only_scan():
    plan = {
        "Node Type": "Index Only Scan",
        "Index Name": "<13625>btree_users_country_id_email",
        "Total Cost": 1787.4,
        "Plan Rows": 34167,
    }

    assert classify_plan(plan) == "index_only_scan"


def test_summarizes_plan():
    plan = {
        "Node Type": "Index Only Scan",
        "Index Name": "<13625>btree_users_country_id_email",
        "Total Cost": 1787.4,
        "Plan Rows": 34167,
    }

    summary = summarize_plan(plan)

    assert summary["root_strategy"] == "index_only_scan"
    assert summary["total_cost"] == 1787.4
    assert summary["estimated_rows"] == 34167
    assert summary["index_names"] == [
        "<13625>btree_users_country_id_email"
    ]
    assert summary["scan_strategies"] == ["index_only_scan"]


def test_join_root_is_not_misclassified_as_child_scan():
    plan = {
        "Node Type": "Nested Loop",
        "Total Cost": 24.58,
        "Plan Rows": 3,
        "Plans": [
            {
                "Node Type": "Index Only Scan",
                "Index Name": "orders_pkey",
                "Total Cost": 10.0,
                "Plan Rows": 1,
            },
            {
                "Node Type": "Index Scan",
                "Index Name": "order_items_order_id_idx",
                "Total Cost": 5.0,
                "Plan Rows": 3,
            },
        ],
    }

    summary = summarize_plan(plan)

    assert summary["root_node"] == "Nested Loop"
    assert summary["root_strategy"] == "other"
    assert summary["scan_strategies"] == [
        "index_only_scan",
        "index_scan",
    ]
    assert len(summary["scan_nodes"]) == 2
