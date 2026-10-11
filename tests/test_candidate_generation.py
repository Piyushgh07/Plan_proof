from app.collector.candidate_generation import generate_candidates


def test_generates_candidate_for_simple_sequential_scan():
    plan = [{
        "Plan": {
            "Node Type": "Seq Scan",
            "Relation Name": "orders",
            "Filter": "(user_id = 123)",
        }
    }]

    candidates = generate_candidates(plan)

    assert len(candidates) == 1
    assert candidates[0].table_name == "orders"
    assert candidates[0].columns == ("user_id",)


def test_skips_sequential_scan_without_filter():
    plan = [{
        "Plan": {
            "Node Type": "Seq Scan",
            "Relation Name": "orders",
        }
    }]

    assert generate_candidates(plan) == []


def test_skips_unknown_table_or_column():
    plan = [{
        "Plan": {
            "Node Type": "Seq Scan",
            "Relation Name": "private_table",
            "Filter": "(secret = 123)",
        }
    }]

    assert generate_candidates(plan) == []


def test_skips_filter_with_multiple_columns():
    plan = [{
        "Plan": {
            "Node Type": "Seq Scan",
            "Relation Name": "orders",
            "Filter": "((user_id = 123) AND (status = 'open'))",
        }
    }]

    assert generate_candidates(plan) == []


def test_walks_nested_plan_nodes():
    plan = [{
        "Plan": {
            "Node Type": "Nested Loop",
            "Plans": [{
                "Node Type": "Seq Scan",
                "Relation Name": "orders",
                "Filter": "(user_id = 123)",
            }],
        }
    }]

    candidates = generate_candidates(plan)

    assert len(candidates) == 1
    assert candidates[0].columns == ("user_id",)


def test_deduplicates_candidates():
    plan = [{
        "Plan": {
            "Node Type": "Append",
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Filter": "(user_id = 123)",
                },
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Filter": "(user_id = 456)",
                },
            ],
        }
    }]

    assert len(generate_candidates(plan)) == 1


def test_generates_candidates_from_hash_join_condition():
    plan = [{
        "Plan": {
            "Node Type": "Hash Join",
            "Join Type": "Anti",
            "Hash Cond": "(oi.order_id = o.id)",
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "order_items",
                    "Alias": "oi",
                },
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Alias": "o",
                },
            ],
        }
    }]

    candidates = generate_candidates(plan)

    assert {
        (candidate.table_name, candidate.columns)
        for candidate in candidates
    } == {
        ("order_items", ("order_id",)),
        ("orders", ("id",)),
    }
