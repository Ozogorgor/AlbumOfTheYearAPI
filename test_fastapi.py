import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Test cache hit/miss logic
def test_cache_hit():
    """Test that cache returns data when not expired"""
    from app.main import get_cached, set_cache
    import app.main as main
    
    # Mock database connection
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (
        {"test": "data"}, datetime.utcnow() - timedelta(days=1)
    )
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    
    with patch.object(main, 'get_db_conn', return_value=mock_conn):
        result = get_cached("test_key")
        assert result == {"test": "data"}

def test_cache_miss_expired():
    """Test that expired cache returns None"""
    from app.main import get_cached
    import app.main as main
    
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (
        {"test": "data"}, datetime.utcnow() - timedelta(days=10)
    )
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    
    with patch.object(main, 'get_db_conn', return_value=mock_conn):
        result = get_cached("test_key")
        assert result is None

def test_cache_miss_no_data():
    """Test that missing cache key returns None"""
    from app.main import get_cached
    import app.main as main
    
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    
    with patch.object(main, 'get_db_conn', return_value=mock_conn):
        result = get_cached("nonexistent_key")
        assert result is None
