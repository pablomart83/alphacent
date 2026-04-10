"""
Unit tests for input validation module.
"""

import pytest
from src.core.validation import InputValidator, ValidationError, InputType


class TestInputValidator:
    """Test InputValidator functionality."""
    
    def test_validate_username_valid(self):
        """Test validation of valid usernames."""
        assert InputValidator.validate_username("testuser") == "testuser"
        assert InputValidator.validate_username("test_user") == "test_user"
        assert InputValidator.validate_username("test-user") == "test-user"
        assert InputValidator.validate_username("user123") == "user123"
    
    def test_validate_username_invalid(self):
        """Test validation of invalid usernames."""
        # Too short
        with pytest.raises(ValidationError):
            InputValidator.validate_username("ab")
        
        # Too long
        with pytest.raises(ValidationError):
            InputValidator.validate_username("a" * 33)
        
        # Invalid characters
        with pytest.raises(ValidationError):
            InputValidator.validate_username("test@user")
        
        # Empty
        with pytest.raises(ValidationError):
            InputValidator.validate_username("")
    
    def test_validate_password_valid(self):
        """Test validation of valid passwords."""
        assert InputValidator.validate_password("TestPass123") == "TestPass123"
        assert InputValidator.validate_password("Secure1Password") == "Secure1Password"
    
    def test_validate_password_invalid(self):
        """Test validation of invalid passwords."""
        # Too short
        with pytest.raises(ValidationError, match="at least 8 characters"):
            InputValidator.validate_password("Short1")
        
        # No uppercase
        with pytest.raises(ValidationError, match="uppercase"):
            InputValidator.validate_password("lowercase123")
        
        # No lowercase
        with pytest.raises(ValidationError, match="lowercase"):
            InputValidator.validate_password("UPPERCASE123")
        
        # No digit
        with pytest.raises(ValidationError, match="digit"):
            InputValidator.validate_password("NoDigits")
        
        # Empty
        with pytest.raises(ValidationError):
            InputValidator.validate_password("")
    
    def test_validate_email_valid(self):
        """Test validation of valid emails."""
        assert InputValidator.validate_email("test@example.com") == "test@example.com"
        assert InputValidator.validate_email("user.name@domain.co.uk") == "user.name@domain.co.uk"
    
    def test_validate_email_invalid(self):
        """Test validation of invalid emails."""
        with pytest.raises(ValidationError):
            InputValidator.validate_email("invalid")
        
        with pytest.raises(ValidationError):
            InputValidator.validate_email("@example.com")
        
        with pytest.raises(ValidationError):
            InputValidator.validate_email("test@")
    
    def test_validate_symbol_valid(self):
        """Test validation of valid trading symbols."""
        assert InputValidator.validate_symbol("AAPL") == "AAPL"
        assert InputValidator.validate_symbol("aapl") == "AAPL"  # Should uppercase
        assert InputValidator.validate_symbol("BTC") == "BTC"
    
    def test_validate_symbol_invalid(self):
        """Test validation of invalid trading symbols."""
        # Too long
        with pytest.raises(ValidationError):
            InputValidator.validate_symbol("TOOLONGSYMBOL")
        
        # Contains numbers
        with pytest.raises(ValidationError):
            InputValidator.validate_symbol("AAPL123")
        
        # Empty
        with pytest.raises(ValidationError):
            InputValidator.validate_symbol("")
    
    def test_validate_numeric_valid(self):
        """Test validation of valid numeric values."""
        assert InputValidator.validate_numeric(123) == 123.0
        assert InputValidator.validate_numeric("456.78") == 456.78
        assert InputValidator.validate_numeric(100, min_value=0, max_value=200) == 100.0
    
    def test_validate_numeric_invalid(self):
        """Test validation of invalid numeric values."""
        # Not a number
        with pytest.raises(ValidationError):
            InputValidator.validate_numeric("not_a_number")
        
        # Below minimum
        with pytest.raises(ValidationError, match="at least"):
            InputValidator.validate_numeric(5, min_value=10)
        
        # Above maximum
        with pytest.raises(ValidationError, match="at most"):
            InputValidator.validate_numeric(100, max_value=50)
    
    def test_validate_alphanumeric_valid(self):
        """Test validation of valid alphanumeric text."""
        assert InputValidator.validate_alphanumeric("test123") == "test123"
        assert InputValidator.validate_alphanumeric("ABC") == "ABC"
    
    def test_validate_alphanumeric_invalid(self):
        """Test validation of invalid alphanumeric text."""
        # Contains special characters
        with pytest.raises(ValidationError):
            InputValidator.validate_alphanumeric("test@123")
        
        # Too short
        with pytest.raises(ValidationError):
            InputValidator.validate_alphanumeric("", min_length=1)
        
        # Too long
        with pytest.raises(ValidationError):
            InputValidator.validate_alphanumeric("a" * 300, max_length=255)
    
    def test_sanitize_text_basic(self):
        """Test basic text sanitization."""
        text = "Hello World"
        sanitized = InputValidator.sanitize_text(text)
        assert sanitized == "Hello World"
    
    def test_sanitize_text_sql_injection(self):
        """Test sanitization of SQL injection attempts."""
        text = "test'; DROP TABLE users; --"
        sanitized = InputValidator.sanitize_text(text)
        
        # Should remove SQL injection patterns
        assert "DROP" not in sanitized
        assert ";" not in sanitized
        assert "--" not in sanitized
    
    def test_sanitize_text_xss(self):
        """Test sanitization of XSS attempts."""
        text = "<script>alert('XSS')</script>"
        sanitized = InputValidator.sanitize_text(text)
        
        # Should remove XSS patterns
        assert "<script>" not in sanitized
        assert "</script>" not in sanitized
    
    def test_sanitize_text_command_injection(self):
        """Test sanitization of command injection attempts."""
        text = "test | rm -rf /"
        sanitized = InputValidator.sanitize_text(text)
        
        # Should remove command injection characters
        assert "|" not in sanitized
    
    def test_sanitize_text_max_length(self):
        """Test text truncation to max length."""
        text = "a" * 2000
        sanitized = InputValidator.sanitize_text(text, max_length=100)
        
        assert len(sanitized) == 100
    
    def test_sanitize_error_message(self):
        """Test error message sanitization."""
        error = "Error in /home/user/secret/file.py at 192.168.1.1 with token abc123def456ghi789"
        sanitized = InputValidator.sanitize_error_message(error)
        
        # Should remove sensitive information
        assert "/home/user/secret/file.py" not in sanitized
        assert "192.168.1.1" not in sanitized
        assert "abc123def456ghi789" not in sanitized
        assert "[path]" in sanitized
        assert "[ip]" in sanitized
        assert "[token]" in sanitized
    
    def test_validate_input_username(self):
        """Test generic validation for username type."""
        result = InputValidator.validate_input("testuser", InputType.USERNAME)
        assert result == "testuser"
    
    def test_validate_input_password(self):
        """Test generic validation for password type."""
        result = InputValidator.validate_input("TestPass123", InputType.PASSWORD)
        assert result == "TestPass123"
    
    def test_validate_input_symbol(self):
        """Test generic validation for symbol type."""
        result = InputValidator.validate_input("aapl", InputType.SYMBOL)
        assert result == "AAPL"
    
    def test_validate_input_numeric(self):
        """Test generic validation for numeric type."""
        result = InputValidator.validate_input("123.45", InputType.NUMERIC)
        assert result == 123.45
    
    def test_validate_input_invalid_type(self):
        """Test validation with unknown input type."""
        with pytest.raises(ValidationError):
            InputValidator.validate_input("test", "unknown_type")
