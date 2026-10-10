from dataclasses import dataclass


@dataclass(frozen=True)
class WorkloadCase:
    query_id: str
    category: str
    sql: str
    problem_exists: bool
    expected_action: str
    expected_index_columns: tuple[str, ...] | None
    expected_index_expression: str | None

WORKLOAD = [
    WorkloadCase(
        query_id="Q001",
        category="missing_index",
        sql="""
            SELECT *
            FROM orders
            WHERE user_id = 12345;
        """,
        problem_exists=True,
        expected_action="CREATE_INDEX",
        expected_index_columns=("user_id",),
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q002",
        category="missing_fk_index",
        sql="""
            SELECT *
            FROM order_items
            WHERE order_id = 123456;
        """,
        problem_exists=True,
        expected_action="CREATE_INDEX",
        expected_index_columns=("order_id",),
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q003",
        category="existing_good_index",
        sql="""
            SELECT *
            FROM products
            WHERE category = 'electronics';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q004",
        category="low_selectivity",
        sql="""
            SELECT *
            FROM users
            WHERE is_active = true;
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q005",
        category="missing_index_sort",
        sql="""
            SELECT *
            FROM events
            WHERE user_id = 12345
            ORDER BY occurred_at DESC
            LIMIT 20;
        """,
        problem_exists=True,
        expected_action="CREATE_INDEX",
        expected_index_columns=("user_id",),
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q006",
        category="existing_good_index",
        sql="""
            SELECT *
            FROM orders
            WHERE created_at >= '2026-09-01';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q007",
        category="existing_composite_index",
        sql="""
            SELECT *
            FROM orders
            WHERE status = 'completed'
              AND created_at >= '2026-09-01';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q008",
        category="missing_fk_index",
        sql="""
            SELECT *
            FROM events
            WHERE user_id = 12345;
        """,
        problem_exists=True,
        expected_action="CREATE_INDEX",
        expected_index_columns=("user_id",),
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q009",
        category="existing_good_index",
        sql="""
            SELECT *
            FROM events
            WHERE event_type = 'login';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q010",
        category="low_selectivity_range",
        sql="""
            SELECT *
            FROM orders
            WHERE created_at >= '2024-01-01';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
        WorkloadCase(
        query_id="Q011",
        category="function_on_column",
        sql="""
            SELECT *
            FROM orders
            WHERE DATE(created_at) = '2026-09-15';
        """,
        problem_exists=True,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q012",
        category="prefix_like",
        sql="""
            SELECT *
            FROM products
            WHERE name LIKE 'phone%';
        """,
        problem_exists=True,
        expected_action="CREATE_INDEX",
        expected_index_columns=("name",),
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q013",
        category="leading_wildcard_like",
        sql="""
            SELECT *
            FROM products
            WHERE name LIKE '%phone%';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q014",
        category="or_predicate",
        sql="""
            SELECT *
            FROM users
            WHERE country = 'IN'
               OR country = 'US';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q015",
        category="missing_fk_index",
        sql="""
            SELECT o.id, oi.product_id, oi.quantity
            FROM orders AS o
            JOIN order_items AS oi
                ON oi.order_id = o.id
            WHERE o.id = 123456;
        """,
        problem_exists=True,
        expected_action="CREATE_INDEX",
        expected_index_columns=("order_id",),
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q016",
        category="aggregation",
        sql="""
            SELECT user_id, COUNT(*)
            FROM orders
            GROUP BY user_id;
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q017",
        category="existing_composite_index",
        sql="""
            SELECT *
            FROM orders
            WHERE created_at >= '2026-09-01'
              AND status = 'completed';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q018",
        category="existing_primary_key",
        sql="""
            SELECT id, name, price
            FROM products
            WHERE id = 12345;
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q019",
        category="existing_date_index",
        sql="""
            SELECT id, user_id, event_type
            FROM events
            WHERE occurred_at >= '2026-09-01'
              AND occurred_at < '2026-09-02';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q020",
        category="low_selectivity",
        sql="""
            SELECT *
            FROM orders
            WHERE total_amount > 1;
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
    query_id="Q021",
    category="join_missing_fk_index",
    sql="""
        SELECT o.id, oi.product_id, oi.quantity
        FROM orders AS o
        JOIN order_items AS oi
            ON oi.order_id = o.id
        WHERE o.created_at >= '2026-09-01';
    """,
    problem_exists=True,
    expected_action="CREATE_INDEX",
    expected_index_columns=("order_id",),
    expected_index_expression=None,
    ),
    WorkloadCase(
    query_id="Q022",
    category="join",
    sql="""
        SELECT p.category, COUNT(*)
        FROM order_items AS oi
        JOIN products AS p
            ON p.id = oi.product_id
        WHERE p.category = 'electronics'
        GROUP BY p.category;
    """,
    problem_exists=False,
    expected_action="NO_CHANGE",
    expected_index_columns=None,
    expected_index_expression=None,
    ),
    WorkloadCase(
    query_id="Q023",
    category="composite_index",
    sql="""
        SELECT *
        FROM orders
        WHERE status = 'shipped'
          AND created_at >= '2026-09-01'
          AND created_at < '2026-10-01';
    """,
    problem_exists=False,
    expected_action="NO_CHANGE",
    expected_index_columns=None,
    expected_index_expression=None,
    ),
    WorkloadCase(
    query_id="Q024",
    category="sort_limit",
    sql="""
        SELECT id, user_id, total_amount
        FROM orders
        ORDER BY created_at DESC
        LIMIT 100;
    """,
    problem_exists=False,
    expected_action="NO_CHANGE",
    expected_index_columns=None,
    expected_index_expression=None,
    ),
   
    WorkloadCase(
    query_id="Q025",
    category="composite_missing_index",
    sql="""
        SELECT *
        FROM orders
        WHERE status = 'cancelled'
          AND total_amount > 1000;
    """,
    problem_exists=True,
    expected_action="CREATE_INDEX",
    expected_index_columns=("status", "total_amount"),
    expected_index_expression=None,
    ),
    WorkloadCase(
    query_id="Q026",
    category="multi_predicate",
    sql="""
        SELECT id, email
        FROM users
        WHERE country = 'IN'
          AND is_active = true;
    """,
    problem_exists=True,
    expected_action="CREATE_INDEX",
    expected_index_columns=("country", "is_active"),
    expected_index_expression=None,
    ),
    WorkloadCase(
    query_id="Q027",
    category="composite_candidate",
    sql="""
        SELECT id, user_id, status
        FROM orders
        WHERE user_id = 12345
          AND status = 'completed';
    """,
    problem_exists=True,
    expected_action="CREATE_INDEX",
    expected_index_columns=("user_id", "status"),
    expected_index_expression=None,
    ),
    WorkloadCase(
    query_id="Q028",
    category="aggregation_filter",
    sql="""
        SELECT status, COUNT(*)
        FROM orders
        WHERE created_at >= '2026-09-01'
        GROUP BY status;
    """,
    problem_exists=False,
    expected_action="NO_CHANGE",
    expected_index_columns=None,
    expected_index_expression=None,
    ),
    WorkloadCase(
    query_id="Q029",
    category="existing_primary_key_join",
    sql="""
        SELECT o.id, u.email
        FROM orders AS o
        JOIN users AS u
            ON u.id = o.user_id
        WHERE u.id = 12345;
    """,
    problem_exists=False,
    expected_action="NO_CHANGE",
    expected_index_columns=None,
    expected_index_expression=None,
    ),
    WorkloadCase(
    query_id="Q030",
    category="full_scan_expected",
    sql="""
        SELECT COUNT(*)
        FROM events;
    """,
    problem_exists=False,
    expected_action="NO_CHANGE",
    expected_index_columns=None,
    expected_index_expression=None,
    ),
        WorkloadCase(
        query_id="Q031",
        category="function_on_column",
        sql="""
            SELECT COUNT(*)
            FROM events
            WHERE DATE(occurred_at) = '2026-09-15';
        """,
        problem_exists=True,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q032",
        category="leading_wildcard_like",
        sql="""
            SELECT id, name
            FROM products
            WHERE name LIKE '%laptop%';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q033",
        category="prefix_like",
        sql="""
            SELECT id, name
            FROM products
            WHERE name LIKE 'laptop%';
        """,
        problem_exists=True,
        expected_action="CREATE_INDEX",
        expected_index_columns=("name",),
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q034",
        category="or_predicate",
        sql="""
            SELECT *
            FROM orders
            WHERE status = 'cancelled'
               OR status = 'returned';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q035",
        category="foreign_key_join",
        sql="""
            SELECT e.id, e.event_type
            FROM events AS e
            JOIN users AS u
                ON u.id = e.user_id
            WHERE u.country = 'IN';
        """,
        problem_exists=True,
        expected_action="CREATE_INDEX",
        expected_index_columns=("user_id",),
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q036",
        category="existing_index_control",
        sql="""
            SELECT *
            FROM products
            WHERE created_at >= '2026-09-01'
              AND created_at < '2026-10-01';
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q037",
        category="low_selectivity",
        sql="""
            SELECT COUNT(*)
            FROM users
            WHERE country IS NOT NULL;
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q038",
        category="aggregation",
        sql="""
            SELECT product_id, SUM(quantity)
            FROM order_items
            GROUP BY product_id;
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q039",
        category="selective_composite_filter",
        sql="""
            SELECT id, email
            FROM users
            WHERE country = 'IN'
              AND is_active = false;
        """,
        problem_exists=True,
        expected_action="CREATE_INDEX",
        expected_index_columns=("country", "is_active"),
        expected_index_expression=None,
    ),
    WorkloadCase(
        query_id="Q040",
        category="full_scan_expected",
        sql="""
            SELECT COUNT(*)
            FROM order_items;
        """,
        problem_exists=False,
        expected_action="NO_CHANGE",
        expected_index_columns=None,
        expected_index_expression=None,
    ),




]

if len(WORKLOAD) != 40:
    raise ValueError("Expected exactly 40 benchmark workload cases")