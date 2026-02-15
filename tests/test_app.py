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

    def test_guide_page_serves_html(self, client):
        resp = client.get('/guide')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Cryptic Crossword' in html or 'cryptic' in html.lower()
        assert '__GA_TRACKING_ID__' not in html
        assert '__SITE_URL__' not in html

    def test_guide_page_has_glossary(self, client):
        resp = client.get('/guide')
        html = resp.data.decode()
        assert 'Anagram' in html
        assert 'Hidden Word' in html
        assert 'Glossary' in html

    def test_robots_txt(self, client):
        resp = client.get('/robots.txt')
        assert resp.status_code == 200
        assert resp.content_type == 'text/plain; charset=utf-8'
        text = resp.data.decode()
        assert 'User-agent: *' in text
        assert '/sitemap.xml' in text
        assert 'cryptic-hints.com' in text
        assert 'Allow: /guide' in text

    def test_sitemap_index(self, client):
        resp = client.get('/sitemap.xml')
        assert resp.status_code == 200
        assert b'<sitemapindex' in resp.data
        assert b'/sitemap-pages.xml' in resp.data
        assert b'/sitemap-puzzles.xml' in resp.data
        assert b'/sitemap-blog.xml' in resp.data
        assert b'/sitemap-clues.xml' in resp.data

    def test_sitemap_pages(self, client):
        resp = client.get('/sitemap-pages.xml')
        assert resp.status_code == 200
        assert b'<urlset' in resp.data
        assert b'/guide' in resp.data
        assert b'/blog' in resp.data

    def test_sitemap_puzzles(self, client, mock_db):
        mock_db.fetchall.return_value = [
            {'puzzle_number': '29001', 'published_at': None},
            {'puzzle_number': '29002', 'published_at': None},
        ]
        resp = client.get('/sitemap-puzzles.xml')
        assert resp.status_code == 200
        assert b'<urlset' in resp.data
        assert b'/puzzle/29001' in resp.data
        assert b'/puzzle/29002' in resp.data

    def test_sitemap_puzzles_db_error(self, client):
        """Sitemap should not 500 on DB error (issue #1 fix)."""
        with patch('production_app.get_db', side_effect=Exception('DB down')):
            resp = client.get('/sitemap-puzzles.xml')
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


# ============================================================================
# Email notification helpers
# ============================================================================

class TestEmailHelpers:
    def test_build_puzzle_email_contains_puzzle_link(self):
        from production_app import _build_puzzle_email
        html = _build_puzzle_email('29001', 'Araucaria')
        assert '/puzzle/29001' in html
        assert 'Araucaria' in html

    def test_build_puzzle_email_unknown_setter(self):
        from production_app import _build_puzzle_email
        html = _build_puzzle_email('29001', 'Unknown')
        assert '/puzzle/29001' in html
        assert 'Unknown' not in html

    def test_send_email_skips_when_no_smtp(self):
        from production_app import _send_email
        with patch('production_app.SMTP_USER', ''), \
             patch('production_app.SMTP_PASSWORD', ''):
            result = _send_email('a@b.com', 'test', '<p>hi</p>')
        assert result is False

    def test_notify_subscribers_skips_when_no_smtp(self):
        from production_app import notify_subscribers
        with patch('production_app.SMTP_USER', ''), \
             patch('production_app.SMTP_PASSWORD', ''):
            # Should not raise, just log and return
            notify_subscribers('29001', 'Araucaria')

    def test_send_email_handles_smtp_failure(self):
        from production_app import _send_email
        with patch('production_app.SMTP_USER', 'user@test.com'), \
             patch('production_app.SMTP_PASSWORD', 'pass'), \
             patch('production_app.smtplib.SMTP_SSL', side_effect=Exception('Connection refused')):
            result = _send_email('a@b.com', 'test', '<p>hi</p>')
        assert result is False

    def test_send_email_success(self):
        from production_app import _send_email
        mock_server = MagicMock()
        mock_smtp_cls = MagicMock(return_value=mock_server)
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)
        with patch('production_app.SMTP_USER', 'info@test.com'), \
             patch('production_app.SMTP_PASSWORD', 'pass'), \
             patch('production_app.smtplib.SMTP_SSL', mock_smtp_cls):
            result = _send_email('a@b.com', 'New Puzzle', '<p>hi</p>')
        assert result is True
        mock_server.login.assert_called_once_with('info@test.com', 'pass')
        mock_server.sendmail.assert_called_once()


# ============================================================================
# Comments
# ============================================================================

class TestComments:
    def test_get_comments_empty(self, client, mock_db):
        mock_db.fetchall.return_value = []
        resp = client.get('/api/puzzle/29001/comments')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data == []

    def test_get_comments_returns_list(self, client, mock_db):
        from datetime import datetime
        ts = datetime(2025, 3, 1, 12, 0, 0)
        mock_db.fetchall.return_value = [
            {'id': 1, 'author': 'Alice', 'body': 'Great puzzle!', 'created_at': ts},
            {'id': 2, 'author': 'Bob', 'body': 'Tricky one.', 'created_at': ts},
        ]
        resp = client.get('/api/puzzle/29001/comments')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 2
        assert data[0]['author'] == 'Alice'
        assert data[1]['body'] == 'Tricky one.'

    def test_post_comment_success(self, client, mock_db):
        from datetime import datetime
        ts = datetime(2025, 3, 1, 12, 0, 0)
        mock_db.fetchone.return_value = {
            'id': 1, 'author': 'Alice', 'body': 'Nice!', 'created_at': ts,
        }
        resp = client.post('/api/puzzle/29001/comments',
                           json={'author': 'Alice', 'body': 'Nice!'})
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data['author'] == 'Alice'
        assert data['body'] == 'Nice!'
        assert data['id'] == 1

    def test_post_comment_missing_author(self, client):
        resp = client.post('/api/puzzle/29001/comments',
                           json={'author': '', 'body': 'Hello'})
        assert resp.status_code == 400

    def test_post_comment_missing_body(self, client):
        resp = client.post('/api/puzzle/29001/comments',
                           json={'author': 'Alice', 'body': ''})
        assert resp.status_code == 400

    def test_post_comment_no_json(self, client):
        resp = client.post('/api/puzzle/29001/comments',
                           data='not json', content_type='text/plain')
        assert resp.status_code in (400, 415)

    def test_post_comment_author_too_long(self, client):
        resp = client.post('/api/puzzle/29001/comments',
                           json={'author': 'A' * 51, 'body': 'Hello'})
        assert resp.status_code == 400

    def test_post_comment_body_too_long(self, client):
        resp = client.post('/api/puzzle/29001/comments',
                           json={'author': 'Alice', 'body': 'x' * 2001})
        assert resp.status_code == 400


# ============================================================================
# Blog - Public
# ============================================================================

class TestBlogPublic:
    def test_blog_listing_page(self, client):
        resp = client.get('/blog')
        assert resp.status_code == 200
        assert b'Blog' in resp.data

    def test_blog_post_page(self, client):
        resp = client.get('/blog/my-first-post')
        assert resp.status_code == 200
        # Slug should be injected
        html = resp.data.decode()
        assert '__BLOG_SLUG__' not in html
        assert 'my-first-post' in html

    def test_get_blog_posts_empty(self, client, mock_db):
        mock_db.fetchall.return_value = []
        resp = client.get('/api/blog/posts')
        assert resp.status_code == 200
        assert json.loads(resp.data) == []

    def test_get_blog_posts_with_data(self, client, mock_db):
        from datetime import datetime
        ts = datetime(2025, 6, 1, 10, 0, 0)
        mock_db.fetchall.return_value = [
            {'id': 1, 'slug': 'test-post', 'title': 'Test Post',
             'meta_description': 'A test', 'published_at': ts},
        ]
        resp = client.get('/api/blog/posts')
        data = json.loads(resp.data)
        assert len(data) == 1
        assert data[0]['slug'] == 'test-post'
        assert data[0]['title'] == 'Test Post'

    def test_get_blog_post_by_slug(self, client, mock_db):
        from datetime import datetime
        ts = datetime(2025, 6, 1, 10, 0, 0)
        mock_db.fetchone.return_value = {
            'id': 1, 'slug': 'test-post', 'title': 'Test Post',
            'meta_description': 'A test', 'body': 'Hello world', 'published_at': ts,
        }
        resp = client.get('/api/blog/posts/test-post')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['body'] == 'Hello world'

    def test_get_blog_post_not_found(self, client, mock_db):
        mock_db.fetchone.return_value = None
        resp = client.get('/api/blog/posts/no-such-post')
        assert resp.status_code == 404


# ============================================================================
# Blog - Admin
# ============================================================================

class TestBlogAdmin:
    def test_admin_blog_requires_login(self, client):
        resp = client.get('/admin/blog')
        assert resp.status_code == 401

    def test_admin_blog_page_accessible(self, logged_in_client):
        resp = logged_in_client.get('/admin/blog')
        assert resp.status_code == 200
        assert b'Blog Manager' in resp.data

    def test_admin_get_blog_posts_requires_login(self, client):
        resp = client.get('/admin/api/blog/posts')
        assert resp.status_code == 401

    def test_admin_create_blog_post(self, logged_in_client, mock_db):
        from datetime import datetime
        ts = datetime(2025, 6, 1, 10, 0, 0)
        mock_db.fetchone.return_value = {
            'id': 1, 'slug': 'my-post', 'title': 'My Post',
            'meta_description': 'Desc', 'body': 'Body text',
            'status': 'draft', 'created_at': ts, 'published_at': None,
        }
        resp = logged_in_client.post('/admin/api/blog/posts',
                                     json={'title': 'My Post', 'body': 'Body text'})
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data['title'] == 'My Post'

    def test_admin_create_blog_post_missing_fields(self, logged_in_client):
        resp = logged_in_client.post('/admin/api/blog/posts',
                                     json={'title': '', 'body': ''})
        assert resp.status_code == 400

    def test_admin_update_blog_post(self, logged_in_client, mock_db):
        mock_db.fetchone.return_value = {
            'id': 1, 'slug': 'my-post', 'title': 'Updated', 'status': 'draft',
        }
        resp = logged_in_client.put('/admin/api/blog/posts/1',
                                    json={'title': 'Updated', 'body': 'New body'})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True

    def test_admin_update_blog_post_not_found(self, logged_in_client, mock_db):
        mock_db.fetchone.return_value = None
        resp = logged_in_client.put('/admin/api/blog/posts/999',
                                    json={'title': 'X', 'body': 'Y'})
        assert resp.status_code == 404

    def test_admin_publish_blog_post(self, logged_in_client, mock_db):
        from datetime import datetime
        mock_db.fetchone.return_value = {
            'id': 1, 'slug': 'my-post', 'title': 'My Post',
            'status': 'published', 'published_at': datetime(2025, 6, 1),
        }
        resp = logged_in_client.post('/admin/api/blog/posts/1/publish')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True

    def test_admin_unpublish_blog_post(self, logged_in_client, mock_db):
        resp = logged_in_client.post('/admin/api/blog/posts/1/unpublish')
        assert resp.status_code == 200

    def test_admin_delete_blog_post(self, logged_in_client, mock_db):
        resp = logged_in_client.delete('/admin/api/blog/posts/1')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True


# ============================================================================
# Individual Clue Pages
# ============================================================================

class TestCluePages:
    def test_clue_page_serves_html(self, client):
        resp = client.get('/clue/29001/3-across')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert '__CLUE_REF__' not in html
        assert '3-across' in html
        assert '29001' in html

    def test_clue_api_returns_clue(self, client, mock_db):
        from datetime import date
        mock_db.fetchone.return_value = {
            'puzzle_number': '29001', 'setter': 'Picaroon',
            'date': date(2025, 6, 1), 'puzzle_type': 'cryptic',
            'id': 42, 'clue_number': '3', 'direction': 'across',
            'clue_text': 'Some clue (5)', 'enumeration': '5',
            'answer': 'TESTS',
            'hint_level_1': 'Hint one', 'hint_level_2': 'Hint two',
            'hint_level_3': 'Hint three', 'hint_level_4': 'Hint four',
        }
        resp = client.get('/api/clue/29001/3-across')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['clue_number'] == '3'
        assert data['direction'] == 'across'
        assert data['clue_text'] == 'Some clue (5)'
        assert data['setter'] == 'Picaroon'
        assert len(data['hints']) == 4

    def test_clue_api_not_found(self, client, mock_db):
        mock_db.fetchone.return_value = None
        resp = client.get('/api/clue/29001/99-across')
        assert resp.status_code == 404

    def test_clue_api_invalid_ref(self, client):
        resp = client.get('/api/clue/29001/bad-format-here')
        assert resp.status_code == 400

    def test_clue_api_invalid_direction(self, client):
        resp = client.get('/api/clue/29001/3-diagonal')
        assert resp.status_code == 400


# ============================================================================
# RSS Feeds
# ============================================================================

class TestRSSFeeds:
    def test_puzzle_feed_returns_xml(self, client, mock_db):
        mock_db.fetchall.return_value = []
        resp = client.get('/feed/puzzles')
        assert resp.status_code == 200
        assert 'application/rss+xml' in resp.content_type
        assert b'<rss' in resp.data
        assert b'Cryptic Hints' in resp.data

    def test_puzzle_feed_with_data(self, client, mock_db):
        from datetime import datetime
        mock_db.fetchall.return_value = [
            {'puzzle_number': '29001', 'setter': 'Picaroon',
             'puzzle_type': 'cryptic', 'published_at': datetime(2025, 6, 1, 10, 0)},
        ]
        resp = client.get('/feed/puzzles')
        assert resp.status_code == 200
        assert b'/puzzle/29001' in resp.data
        assert b'Picaroon' in resp.data

    def test_puzzle_feed_db_error(self, client):
        with patch('production_app.get_db', side_effect=Exception('DB down')):
            resp = client.get('/feed/puzzles')
        assert resp.status_code == 200
        assert b'<rss' in resp.data

    def test_blog_feed_returns_xml(self, client, mock_db):
        mock_db.fetchall.return_value = []
        resp = client.get('/feed/blog')
        assert resp.status_code == 200
        assert 'application/rss+xml' in resp.content_type
        assert b'<rss' in resp.data

    def test_blog_feed_with_data(self, client, mock_db):
        from datetime import datetime
        mock_db.fetchall.return_value = [
            {'slug': 'my-post', 'title': 'My Post',
             'meta_description': 'A summary', 'published_at': datetime(2025, 6, 1)},
        ]
        resp = client.get('/feed/blog')
        assert resp.status_code == 200
        assert b'/blog/my-post' in resp.data
        assert b'My Post' in resp.data

    def test_sitemap_clues(self, client, mock_db):
        mock_db.fetchall.return_value = [
            {'puzzle_number': '29001', 'clue_number': '1', 'direction': 'across', 'published_at': None},
        ]
        resp = client.get('/sitemap-clues.xml')
        assert resp.status_code == 200
        assert b'/clue/29001/1-across' in resp.data

    def test_sitemap_blog(self, client, mock_db):
        mock_db.fetchall.return_value = [
            {'slug': 'test-post', 'published_at': None},
        ]
        resp = client.get('/sitemap-blog.xml')
        assert resp.status_code == 200
        assert b'/blog/test-post' in resp.data
