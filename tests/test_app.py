"""Tests for Flask application routes."""
import json
from decimal import Decimal
from unittest.mock import patch, MagicMock


# Fixtures (app, client, logged_in_client, mock_db) come from conftest.py


# ============================================================================
# Public routes
# ============================================================================

class TestPublicRoutes:
    def test_homepage_serves_html(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'Cryptic Hints' in resp.data

    def test_homepage_injects_config(self, client):
        resp = client.get('/')
        html = resp.data.decode()
        # Placeholders should be replaced
        assert '__SITE_URL__' not in html
        assert '__GA_TRACKING_ID__' not in html
        # Actual values (defaults) should be present
        assert 'cryptic-hints.com' in html
        assert 'G-EN3G45Y8DB' in html

    def test_puzzle_page_serves_html(self, client):
        resp = client.get('/puzzle/12345')
        assert resp.status_code == 200
        assert b'Guardian Cryptic Crossword' in resp.data

    def test_puzzle_page_injects_ga_id(self, client):
        resp = client.get('/puzzle/12345')
        html = resp.data.decode()
        assert '__GA_TRACKING_ID__' not in html

    def test_robots_txt(self, client):
        resp = client.get('/robots.txt')
        assert resp.status_code == 200
        assert resp.content_type == 'text/plain; charset=utf-8'
        text = resp.data.decode()
        assert 'User-agent: *' in text
        assert '/sitemap.xml' in text
        assert 'cryptic-hints.com' in text

    def test_sitemap_xml_with_puzzles(self, client, mock_db):
        mock_db.fetchall.return_value = [
            {'puzzle_number': '29001', 'published_at': None},
            {'puzzle_number': '29002', 'published_at': None},
        ]
        resp = client.get('/sitemap.xml')
        assert resp.status_code == 200
        assert b'<urlset' in resp.data
        assert b'/puzzle/29001' in resp.data
        assert b'/puzzle/29002' in resp.data

    def test_sitemap_xml_db_error_returns_empty(self, client):
        """Sitemap should not 500 on DB error (issue #1 fix)."""
        with patch('production_app.get_db', side_effect=Exception('DB down')):
            resp = client.get('/sitemap.xml')
        assert resp.status_code == 200
        assert b'<urlset' in resp.data


# ============================================================================
# API routes
# ============================================================================

class TestPublicAPI:
    def test_get_published_puzzles(self, client, mock_db):
        mock_db.fetchall.return_value = [
            {'id': 1, 'publication': 'Guardian', 'puzzle_number': '29001',
             'setter': 'Araucaria', 'date': '2025-01-01', 'clue_count': 28}
        ]
        resp = client.get('/api/puzzles/published')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 1
        assert data[0]['puzzle_number'] == '29001'

    def test_get_puzzle_by_number_not_found(self, client, mock_db):
        mock_db.fetchone.return_value = None
        resp = client.get('/api/puzzle/99999')
        assert resp.status_code == 404

    def test_get_clue_hints(self, client, mock_db):
        mock_db.fetchone.return_value = {
            'hint_level_1': 'Definition hint',
            'hint_level_2': 'Wordplay hint',
            'hint_level_3': 'Breakdown hint',
            'hint_level_4': 'Full explanation',
        }
        resp = client.get('/api/clue/1/hints')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data['hints']) == 4
        assert data['hints'][0] == 'Definition hint'

    def test_get_clue_hints_not_found(self, client, mock_db):
        mock_db.fetchone.return_value = None
        resp = client.get('/api/clue/99999/hints')
        assert resp.status_code == 404

    def test_check_answer_correct(self, client, mock_db):
        mock_db.fetchone.return_value = {
            'answer': 'CROSSWORD',
            'clue_text': 'Test clue',
        }
        resp = client.post('/api/clue/1/check',
                           json={'answer': 'crossword'})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['correct'] is True

    def test_check_answer_incorrect(self, client, mock_db):
        mock_db.fetchone.return_value = {
            'answer': 'CROSSWORD',
            'clue_text': 'Test clue',
        }
        resp = client.post('/api/clue/1/check',
                           json={'answer': 'WRONG'})
        data = json.loads(resp.data)
        assert data['correct'] is False

    def test_check_answer_no_body(self, client):
        resp = client.post('/api/clue/1/check',
                           json={'answer': ''})
        assert resp.status_code == 400

    def test_invalid_hint_level(self, client):
        resp = client.get('/api/clue/1/hint/5')
        assert resp.status_code == 400


# ============================================================================
# Admin auth
# ============================================================================

class TestAdminAuth:
    def test_admin_requires_login(self, client):
        resp = client.get('/admin')
        assert resp.status_code == 401

    def test_admin_api_requires_login(self, client):
        resp = client.get('/admin/api/puzzles/all')
        assert resp.status_code == 401

    def test_admin_usage_requires_login(self, client):
        resp = client.get('/admin/api/usage')
        assert resp.status_code == 401

    def test_admin_accessible_when_logged_in(self, logged_in_client):
        resp = logged_in_client.get('/admin')
        assert resp.status_code == 200

    def test_admin_usage_page_accessible(self, logged_in_client):
        resp = logged_in_client.get('/admin/usage')
        assert resp.status_code == 200
        assert b'API Usage' in resp.data


# ============================================================================
# Admin API - Hint level validation (SQL injection prevention)
# ============================================================================

class TestHintLevelValidation:
    def test_update_hint_rejects_invalid_level(self, logged_in_client):
        resp = logged_in_client.post('/admin/api/hint/update',
                                     json={'clue_id': 1, 'hint_level': 99, 'new_text': 'x'})
        assert resp.status_code == 400

    def test_update_hint_rejects_string_level(self, logged_in_client):
        resp = logged_in_client.post('/admin/api/hint/update',
                                     json={'clue_id': 1, 'hint_level': '1; DROP TABLE clues--', 'new_text': 'x'})
        assert resp.status_code == 400

    def test_approve_hint_rejects_invalid_level(self, logged_in_client):
        resp = logged_in_client.post('/admin/api/hint/approve',
                                     json={'clue_id': 1, 'hint_level': 0})
        assert resp.status_code == 400

    def test_flag_hint_rejects_invalid_level(self, logged_in_client):
        resp = logged_in_client.post('/admin/api/hint/flag',
                                     json={'clue_id': 1, 'hint_level': 5})
        assert resp.status_code == 400

    def test_approve_hint_accepts_valid_level(self, logged_in_client, mock_db):
        resp = logged_in_client.post('/admin/api/hint/approve',
                                     json={'clue_id': 1, 'hint_level': 2})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True

    def test_flag_hint_accepts_valid_level(self, logged_in_client, mock_db):
        resp = logged_in_client.post('/admin/api/hint/flag',
                                     json={'clue_id': 1, 'hint_level': 4})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True


# ============================================================================
# Admin API - Usage tracking
# ============================================================================

class TestAdminUsageAPI:
    def test_usage_endpoint_returns_structure(self, logged_in_client, mock_db):
        mock_db.fetchall.return_value = []
        mock_db.fetchone.return_value = {
            'total_calls': 0,
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_tokens': 0,
            'total_cost_usd': 0,
            'total_imports': 0,
        }
        resp = logged_in_client.get('/admin/api/usage')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'imports' in data
        assert 'totals' in data
        assert data['totals']['total_calls'] == 0

    def test_usage_with_data(self, logged_in_client, mock_db):
        mock_db.fetchall.return_value = [
            {'id': 1, 'puzzle_number': '29001', 'api_calls': 28,
             'input_tokens': 14000, 'output_tokens': 5600,
             'total_tokens': 19600, 'estimated_cost_usd': Decimal('0.126'),
             'model': 'claude-sonnet-4-20250514',
             'created_at': '2025-02-06T10:00:00'},
        ]
        mock_db.fetchone.return_value = {
            'total_calls': 28,
            'total_input_tokens': 14000,
            'total_output_tokens': 5600,
            'total_tokens': 19600,
            'total_cost_usd': Decimal('0.126'),
            'total_imports': 1,
        }
        resp = logged_in_client.get('/admin/api/usage')
        data = json.loads(resp.data)
        assert len(data['imports']) == 1
        assert data['imports'][0]['puzzle_number'] == '29001'
        assert data['totals']['total_imports'] == 1


# ============================================================================
# Email subscription
# ============================================================================

class TestSubscribe:
    def test_subscribe_success(self, client, mock_db):
        resp = client.post('/api/subscribe', json={'email': 'test@example.com'})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True
        assert 'subscribing' in data['message'].lower() or 'notified' in data['message'].lower()

    def test_subscribe_invalid_email(self, client):
        resp = client.post('/api/subscribe', json={'email': 'not-an-email'})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_subscribe_empty_email(self, client):
        resp = client.post('/api/subscribe', json={'email': ''})
        assert resp.status_code == 400

    def test_subscribe_missing_email(self, client):
        resp = client.post('/api/subscribe', json={})
        assert resp.status_code == 400

    def test_unsubscribe_success(self, client, mock_db):
        resp = client.post('/api/unsubscribe', json={'email': 'test@example.com'})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True

    def test_unsubscribe_empty_email(self, client):
        resp = client.post('/api/unsubscribe', json={'email': ''})
        assert resp.status_code == 400


class TestAdminSubscribers:
    def test_subscribers_requires_login(self, client):
        resp = client.get('/admin/api/subscribers')
        assert resp.status_code == 401

    def test_subscribers_page_accessible(self, logged_in_client):
        resp = logged_in_client.get('/admin/subscribers')
        assert resp.status_code == 200
        assert b'Subscribers' in resp.data

    def test_subscribers_api_returns_structure(self, logged_in_client, mock_db):
        mock_db.fetchall.return_value = []
        mock_db.fetchone.return_value = {
            'total': 0, 'active': 0, 'unsubscribed': 0,
        }
        resp = logged_in_client.get('/admin/api/subscribers')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'subscribers' in data
        assert 'counts' in data
        assert data['counts']['total'] == 0

    def test_subscribers_api_with_data(self, logged_in_client, mock_db):
        mock_db.fetchall.return_value = [
            {'id': 1, 'email': 'a@b.com', 'subscribed_at': '2025-02-06',
             'confirmed': False, 'unsubscribed_at': None},
        ]
        mock_db.fetchone.return_value = {
            'total': 1, 'active': 1, 'unsubscribed': 0,
        }
        resp = logged_in_client.get('/admin/api/subscribers')
        data = json.loads(resp.data)
        assert len(data['subscribers']) == 1
        assert data['subscribers'][0]['email'] == 'a@b.com'
        assert data['counts']['active'] == 1

    def test_delete_subscriber_requires_login(self, client):
        resp = client.delete('/admin/api/subscriber/1')
        assert resp.status_code == 401

    def test_delete_subscriber(self, logged_in_client, mock_db):
        resp = logged_in_client.delete('/admin/api/subscriber/1')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True
