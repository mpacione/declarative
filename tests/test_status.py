"""Tests for status reporting functions."""


import pytest

from dd.db import init_db
from dd.status import (
    format_status_report,
    get_curation_progress,
    get_export_readiness,
    get_status_dict,
    get_token_coverage,
    get_unbound_summary,
)


@pytest.fixture
def empty_db():
    """Create an empty database."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def test_db():
    """Create a database with test data."""
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("""
        INSERT INTO files (id, file_key, name, extracted_at)
        VALUES (1, 'test_file', 'Test File', '2024-01-01T00:00:00Z')
    """)

    conn.execute("""
        INSERT INTO token_collections (id, file_id, name)
        VALUES (1, 1, 'Test Collection')
    """)

    conn.execute("""
        INSERT INTO token_modes (id, collection_id, name, is_default)
        VALUES (1, 1, 'Light', 1), (2, 1, 'Dark', 0)
    """)

    # Add tokens
    conn.executemany("""
        INSERT INTO tokens (id, collection_id, name, type, tier)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (1, 1, 'color.surface.primary', 'color', 'curated'),
        (2, 1, 'color.surface.secondary', 'color', 'extracted'),
        (3, 1, 'space.4', 'dimension', 'curated'),
        (4, 1, 'space.8', 'dimension', 'extracted'),
    ])

    # Add token values
    conn.executemany("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (?, ?, ?, ?)
    """, [
        (1, 1, '#FF0000', '#FF0000'),
        (1, 2, '#CC0000', '#CC0000'),
        (2, 1, '#00FF00', '#00FF00'),
        (2, 2, '#00CC00', '#00CC00'),
        (3, 1, '16px', '16'),
        (3, 2, '16px', '16'),
        (4, 1, '32px', '32'),
        (4, 2, '32px', '32'),
    ])

    # Add screens
    conn.executemany("""
        INSERT INTO screens (id, file_id, figma_node_id, name, width, height, device_class)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        (1, 1, 'screen1', 'Home Screen', 1920, 1080, 'web'),
        (2, 1, 'screen2', 'About Screen', 1920, 1080, 'web'),
    ])

    # Add nodes
    conn.executemany("""
        INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, node_type, depth, sort_order, is_semantic)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (1, 1, 'node1', None, 'Header', 'FRAME', 0, 0, 1),
        (2, 1, 'node2', 1, 'Title', 'TEXT', 1, 0, 1),
        (3, 2, 'node3', None, 'Content', 'FRAME', 0, 0, 1),
        (4, 2, 'node4', 3, 'Paragraph', 'TEXT', 1, 0, 1),
    ])

    # Add bindings with various statuses
    conn.executemany("""
        INSERT INTO node_token_bindings
        (id, node_id, property, token_id, raw_value, resolved_value, confidence, binding_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        # Bound bindings (50%)
        (1, 1, 'fill.0.color', 1, '#FF0000', '#FF0000', 0.95, 'bound'),
        (2, 1, 'padding.top', 3, '16px', '16', 0.99, 'bound'),
        (3, 2, 'fill.0.color', 1, '#FF0000', '#FF0000', 0.95, 'bound'),
        (4, 2, 'fontSize', 3, '16px', '16', 0.99, 'bound'),
        (5, 3, 'fill.0.color', 1, '#FF0000', '#FF0000', 0.95, 'bound'),

        # Proposed bindings (30%)
        (6, 3, 'padding.top', 4, '32px', '32', 0.85, 'proposed'),
        (7, 4, 'fill.0.color', 2, '#00FF00', '#00FF00', 0.85, 'proposed'),
        (8, 4, 'fontSize', 4, '32px', '32', 0.85, 'proposed'),

        # Unbound bindings (10%)
        (9, 1, 'border.color', None, '#ABC123', '#ABC123', None, 'unbound'),

        # Overridden bindings (10%)
        (10, 3, 'margin.top', 3, '16px', '16', 0.95, 'overridden'),
    ])

    # Add export validations
    conn.executemany("""
        INSERT INTO export_validations (check_name, severity, message, run_at, resolved)
        VALUES (?, ?, ?, ?, ?)
    """, [
        ('mode_completeness', 'warning', 'Token missing value in Dark mode', '2024-01-02T00:00:00Z', 0),
        ('mode_completeness', 'warning', 'Another token missing value', '2024-01-02T00:00:00Z', 0),
        ('orphan_tokens', 'warning', 'Token not used in any bindings', '2024-01-02T00:00:00Z', 0),
        ('orphan_tokens', 'warning', 'Another unused token', '2024-01-02T00:00:00Z', 0),
        ('name_dtcg_compliant', 'info', 'All names are compliant', '2024-01-02T00:00:00Z', 0),
    ])

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def multi_file_db():
    """Create a database with multiple files."""
    conn = init_db(":memory:")

    # Insert two files
    conn.executemany("""
        INSERT INTO files (id, file_key, name, extracted_at)
        VALUES (?, ?, ?, ?)
    """, [
        (1, 'file1', 'File 1', '2024-01-01T00:00:00Z'),
        (2, 'file2', 'File 2', '2024-01-01T00:00:00Z'),
    ])

    # Collections for each file
    conn.executemany("""
        INSERT INTO token_collections (id, file_id, name)
        VALUES (?, ?, ?)
    """, [
        (1, 1, 'Collection 1'),
        (2, 2, 'Collection 2'),
    ])

    # Mode for each collection
    conn.executemany("""
        INSERT INTO token_modes (id, collection_id, name, is_default)
        VALUES (?, ?, ?, ?)
    """, [
        (1, 1, 'Light', 1),
        (2, 2, 'Light', 1),
    ])

    # Tokens in each collection
    conn.executemany("""
        INSERT INTO tokens (id, collection_id, name, type, tier)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (1, 1, 'color.primary', 'color', 'curated'),
        (2, 1, 'space.small', 'dimension', 'extracted'),
        (3, 2, 'color.secondary', 'color', 'curated'),
        (4, 2, 'space.large', 'dimension', 'extracted'),
    ])

    # Screens for each file
    conn.executemany("""
        INSERT INTO screens (id, file_id, figma_node_id, name, width, height, device_class)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        (1, 1, 'screen1', 'Screen 1', 1920, 1080, 'web'),
        (2, 2, 'screen2', 'Screen 2', 1920, 1080, 'web'),
    ])

    # Nodes and bindings
    conn.executemany("""
        INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, node_type, depth, sort_order, is_semantic)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (1, 1, 'node1', None, 'Node 1', 'FRAME', 0, 0, 1),
        (2, 2, 'node2', None, 'Node 2', 'FRAME', 0, 0, 1),
    ])

    conn.executemany("""
        INSERT INTO node_token_bindings
        (node_id, property, token_id, raw_value, resolved_value, confidence, binding_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        (1, 'fill.0.color', 1, '#FF0000', '#FF0000', 0.95, 'bound'),
        (1, 'padding.top', 2, '8px', '8', 0.85, 'proposed'),
        (1, 'margin.top', None, '16px', '16', None, 'unbound'),
        (2, 'fill.0.color', 3, '#00FF00', '#00FF00', 0.95, 'bound'),
        (2, 'padding.top', 4, '32px', '32', 0.85, 'proposed'),
    ])

    conn.commit()
    yield conn
    conn.close()


class TestCurationProgress:
    def test_get_curation_progress(self, test_db):
        result = get_curation_progress(test_db)

        assert isinstance(result, list)
        assert len(result) == 4  # bound, proposed, overridden, unbound

        # Check that we have the right statuses and percentages
        status_map = {row['status']: row for row in result}

        assert 'bound' in status_map
        assert status_map['bound']['count'] == 5
        assert status_map['bound']['pct'] == 50.0

        assert 'proposed' in status_map
        assert status_map['proposed']['count'] == 3
        assert status_map['proposed']['pct'] == 30.0

        assert 'unbound' in status_map
        assert status_map['unbound']['count'] == 1
        assert status_map['unbound']['pct'] == 10.0

        assert 'overridden' in status_map
        assert status_map['overridden']['count'] == 1
        assert status_map['overridden']['pct'] == 10.0

    def test_get_curation_progress_empty_db(self, empty_db):
        result = get_curation_progress(empty_db)
        assert result == []


class TestTokenCoverage:
    def test_get_token_coverage(self, test_db):
        result = get_token_coverage(test_db)

        assert isinstance(result, list)
        assert len(result) == 4  # 4 tokens in test data

        # Should be sorted by binding_count descending
        assert result[0]['token_name'] == 'color.surface.primary'
        assert result[0]['binding_count'] == 3
        assert result[0]['node_count'] == 3
        assert result[0]['screen_count'] == 2

        # Token with proposed bindings
        assert result[1]['token_name'] == 'space.4'
        assert result[1]['binding_count'] == 3  # 2 bound + 1 overridden

        # Tokens with fewer bindings
        for token in result[2:]:
            assert token['binding_count'] > 0

    def test_get_token_coverage_with_file_id(self, multi_file_db):
        result = get_token_coverage(multi_file_db, file_id=1)

        assert len(result) == 2  # Only tokens from file 1
        assert all(t['token_name'] in ['color.primary', 'space.small'] for t in result)

    def test_get_token_coverage_empty_db(self, empty_db):
        result = get_token_coverage(empty_db)
        assert result == []


class TestUnboundSummary:
    def test_get_unbound_summary(self, test_db):
        result = get_unbound_summary(test_db)

        assert isinstance(result, list)
        assert len(result) == 1  # Only 1 unbound binding

        binding = result[0]
        assert binding['binding_id'] == 9
        assert binding['screen_name'] == 'Home Screen'
        assert binding['node_name'] == 'Header'
        assert binding['property'] == 'border.color'
        assert binding['resolved_value'] == '#ABC123'

    def test_get_unbound_summary_with_limit(self, test_db):
        # Add more unbound bindings
        for i in range(10):
            test_db.execute("""
                INSERT INTO node_token_bindings
                (node_id, property, token_id, raw_value, resolved_value, confidence, binding_status)
                VALUES (1, ?, NULL, '24px', '24', NULL, 'unbound')
            """, (f'margin.{i}',))
        test_db.commit()

        result = get_unbound_summary(test_db, limit=5)
        assert len(result) == 5

    def test_get_unbound_summary_with_file_id(self, multi_file_db):
        result = get_unbound_summary(multi_file_db, file_id=1)

        assert len(result) == 1
        assert result[0]['resolved_value'] == '16'

    def test_get_unbound_summary_empty_db(self, empty_db):
        result = get_unbound_summary(empty_db)
        assert result == []


class TestExportReadiness:
    def test_get_export_readiness(self, test_db):
        result = get_export_readiness(test_db)

        assert isinstance(result, list)
        assert len(result) == 3  # 3 distinct check_name/severity combos

        # Should be sorted by severity (error, warning, info)
        for check in result:
            if check['check_name'] == 'mode_completeness':
                assert check['severity'] == 'warning'
                assert check['issue_count'] == 2
                assert check['resolved_count'] == 0
            elif check['check_name'] == 'orphan_tokens':
                assert check['severity'] == 'warning'
                assert check['issue_count'] == 2
            elif check['check_name'] == 'name_dtcg_compliant':
                assert check['severity'] == 'info'
                assert check['issue_count'] == 1

    def test_get_export_readiness_no_validation(self, empty_db):
        result = get_export_readiness(empty_db)
        assert result == []


class TestStatusReport:
    def test_format_status_report(self, test_db):
        report = format_status_report(test_db)

        assert isinstance(report, str)
        assert '=== Curation Progress ===' in report
        assert '=== Token Coverage ===' in report
        assert '=== Unbound Bindings ===' in report
        assert '=== Export Readiness ===' in report

        # Check specific content
        assert 'bound' in report
        assert '50.0%' in report
        assert 'color.surface.primary' in report
        assert '1 bindings remain unbound' in report
        assert 'PASS: 0 errors, 4 warnings' in report

    def test_format_status_report_empty_db(self, empty_db):
        report = format_status_report(empty_db)

        assert isinstance(report, str)
        assert '=== Curation Progress ===' in report
        assert 'No bindings found' in report
        assert 'Total tokens: 0' in report
        assert '0 bindings remain unbound' in report
        assert '[not yet validated]' in report

    def test_format_status_report_with_file_id(self, multi_file_db):
        report = format_status_report(multi_file_db, file_id=1)

        assert 'color.primary' in report
        assert 'color.secondary' not in report  # From file 2


class TestStatusDict:
    def test_get_status_dict(self, test_db):
        result = get_status_dict(test_db)

        assert isinstance(result, dict)
        assert 'curation_progress' in result
        assert 'token_count' in result
        assert 'token_coverage' in result
        assert 'unbound_count' in result
        assert 'export_readiness' in result
        assert 'is_ready' in result

        assert result['token_count'] == 4
        assert result['unbound_count'] == 1
        assert len(result['token_coverage']) <= 10  # Top 10 only
        assert result['is_ready'] is True  # No errors, only warnings

    def test_get_status_dict_no_validation(self, empty_db):
        result = get_status_dict(empty_db)

        assert result['is_ready'] is False  # No validation run
        assert result['token_count'] == 0
        assert result['unbound_count'] == 0

    def test_get_status_dict_with_errors(self, test_db):
        # Add an error validation
        test_db.execute("""
            INSERT INTO export_validations (check_name, severity, message, run_at, resolved)
            VALUES ('critical_check', 'error', 'Critical issue', '2024-01-02T00:00:00Z', 0)
        """)
        test_db.commit()

        result = get_status_dict(test_db)
        assert result['is_ready'] is False  # Has errors