"""
Input validation and sanitization module for AlphaCent Trading Platform.

Provides validation and sanitization for all user inputs to prevent injection attacks.
"""

import re
import logging
from typing import Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Exception raised for validation errors."""
    pass


class InputType(Enum):
    """Types of inputs for validation."""
    USERNAME = "username"
    PASSWORD = "password"
    EMAIL = "email"
    SYMBOL = "symbol"
    NUMERIC = "numeric"
    ALPHANUMERIC = "alphanumeric"
    TEXT = "text"
    API_KEY = "api_key"


class InputValidator:
    """
    Validates and sanitizes user inputs to prevent injection attacks.
    
    Validates: Requirement 18.6, Property 32
    """
    
    # Validation patterns
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,32}$')
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    SYMBOL_PATTERN = re.compile(r'^[A-Z]{1,10}$')
    ALPHANUMERIC_PATTERN = re.compile(r'^[a-zA-Z0-9]+$')
    API_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{16,128}$')
    
    # Dangerous characters for injection attacks
    SQL_INJECTION_CHARS = ["'", '"', ';', '--', '/*', '*/', 'xp_', 'sp_', 'DROP', 'DELETE', 'INSERT', 'UPDATE']
    XSS_CHARS = ['<script>', '</script>', '<iframe>', '</iframe>', 'javascript:', 'onerror=', 'onload=']
    COMMAND_INJECTION_CHARS = ['|', '&', ';', '$', '`', '\n', '\r']
    
    @staticmethod
    def validate_username(username: str) -> str:
        """
        Validate username format.
        
        Args:
            username: Username to validate
            
        Returns:
            Validated username
            
        Raises:
            ValidationError: If username is invalid
            
        Validates: Requirement 18.6
        """
        if not username:
            raise ValidationError("Username cannot be empty")
        
        if not InputValidator.USERNAME_PATTERN.match(username):
            logger.warning(f"Invalid username format: {username[:10]}...")
            raise ValidationError(
                "Username must be 3-32 characters and contain only letters, numbers, hyphens, and underscores"
            )
        
        return username
    
    @staticmethod
    def validate_password(password: str) -> str:
        """
        Validate password strength.
        
        Args:
            password: Password to validate
            
        Returns:
            Validated password
            
        Raises:
            ValidationError: If password is invalid
            
        Validates: Requirement 18.6
        """
        if not password:
            raise ValidationError("Password cannot be empty")
        
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters")
        
        if len(password) > 128:
            raise ValidationError("Password must be less than 128 characters")
        
        # Check for basic complexity
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        
        if not (has_upper and has_lower and has_digit):
            raise ValidationError(
                "Password must contain at least one uppercase letter, one lowercase letter, and one digit"
            )
        
        return password
    
    @staticmethod
    def validate_email(email: str) -> str:
        """
        Validate email format.
        
        Args:
            email: Email to validate
            
        Returns:
            Validated email
            
        Raises:
            ValidationError: If email is invalid
        """
        if not email:
            raise ValidationError("Email cannot be empty")
        
        if not InputValidator.EMAIL_PATTERN.match(email):
            logger.warning(f"Invalid email format: {email[:20]}...")
            raise ValidationError("Invalid email format")
        
        return email.lower()
    
    @staticmethod
    def validate_symbol(symbol: str) -> str:
        """
        Validate trading symbol format.
        
        Args:
            symbol: Trading symbol to validate
            
        Returns:
            Validated symbol (uppercase)
            
        Raises:
            ValidationError: If symbol is invalid
            
        Validates: Requirement 18.6
        """
        if not symbol:
            raise ValidationError("Symbol cannot be empty")
        
        symbol = symbol.upper()
        
        if not InputValidator.SYMBOL_PATTERN.match(symbol):
            logger.warning(f"Invalid symbol format: {symbol}")
            raise ValidationError("Symbol must be 1-10 uppercase letters")
        
        return symbol
    
    @staticmethod
    def validate_numeric(value: Any, min_value: Optional[float] = None, 
                        max_value: Optional[float] = None) -> float:
        """
        Validate numeric input.
        
        Args:
            value: Value to validate
            min_value: Minimum allowed value (optional)
            max_value: Maximum allowed value (optional)
            
        Returns:
            Validated numeric value
            
        Raises:
            ValidationError: If value is invalid
            
        Validates: Requirement 18.6
        """
        try:
            numeric_value = float(value)
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid numeric value: {value}")
        
        if min_value is not None and numeric_value < min_value:
            raise ValidationError(f"Value must be at least {min_value}")
        
        if max_value is not None and numeric_value > max_value:
            raise ValidationError(f"Value must be at most {max_value}")
        
        return numeric_value
    
    @staticmethod
    def validate_alphanumeric(text: str, min_length: int = 1, max_length: int = 255) -> str:
        """
        Validate alphanumeric text.
        
        Args:
            text: Text to validate
            min_length: Minimum length
            max_length: Maximum length
            
        Returns:
            Validated text
            
        Raises:
            ValidationError: If text is invalid
        """
        if not text:
            raise ValidationError("Text cannot be empty")
        
        if len(text) < min_length:
            raise ValidationError(f"Text must be at least {min_length} characters")
        
        if len(text) > max_length:
            raise ValidationError(f"Text must be at most {max_length} characters")
        
        if not InputValidator.ALPHANUMERIC_PATTERN.match(text):
            raise ValidationError("Text must contain only letters and numbers")
        
        return text
    
    @staticmethod
    def validate_api_key(api_key: str) -> str:
        """
        Validate API key format.
        
        Args:
            api_key: API key to validate
            
        Returns:
            Validated API key
            
        Raises:
            ValidationError: If API key is invalid
        """
        if not api_key:
            raise ValidationError("API key cannot be empty")
        
        if not InputValidator.API_KEY_PATTERN.match(api_key):
            logger.warning("Invalid API key format")
            raise ValidationError("Invalid API key format")
        
        return api_key
    
    @staticmethod
    def sanitize_text(text: str, max_length: int = 1000) -> str:
        """
        Sanitize text input to prevent injection attacks.
        
        Args:
            text: Text to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Sanitized text
            
        Validates: Requirement 18.6, Property 32
        """
        if not text:
            return ""
        
        # Truncate to max length
        sanitized = text[:max_length]
        
        # Remove null bytes
        sanitized = sanitized.replace('\x00', '')
        
        # Check for SQL injection patterns
        for pattern in InputValidator.SQL_INJECTION_CHARS:
            if pattern.lower() in sanitized.lower():
                logger.warning(f"Potential SQL injection detected: {pattern}")
                sanitized = sanitized.replace(pattern, '')
        
        # Check for XSS patterns
        for pattern in InputValidator.XSS_CHARS:
            if pattern.lower() in sanitized.lower():
                logger.warning(f"Potential XSS detected: {pattern}")
                sanitized = sanitized.replace(pattern, '')
        
        # Check for command injection patterns
        for char in InputValidator.COMMAND_INJECTION_CHARS:
            if char in sanitized:
                logger.warning(f"Potential command injection detected: {char}")
                sanitized = sanitized.replace(char, '')
        
        return sanitized.strip()
    
    @staticmethod
    def sanitize_error_message(error_message: str) -> str:
        """
        Sanitize error message to prevent information leakage.
        
        Args:
            error_message: Original error message
            
        Returns:
            Sanitized error message safe for display
            
        Validates: Requirement 18.6
        """
        # Remove sensitive information patterns
        sanitized = error_message
        
        # Remove file paths
        sanitized = re.sub(r'/[a-zA-Z0-9_/.-]+', '[path]', sanitized)
        sanitized = re.sub(r'[A-Z]:\\[a-zA-Z0-9_\\.-]+', '[path]', sanitized)
        
        # Remove IP addresses
        sanitized = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '[ip]', sanitized)
        
        # Remove API keys/tokens (long alphanumeric strings)
        sanitized = re.sub(r'[a-zA-Z0-9_-]{16,}', '[token]', sanitized)
        
        # Truncate to reasonable length
        if len(sanitized) > 200:
            sanitized = sanitized[:200] + "..."
        
        return sanitized
    
    @staticmethod
    def validate_input(value: Any, input_type: InputType, **kwargs) -> Any:
        """
        Generic input validation based on type.
        
        Args:
            value: Value to validate
            input_type: Type of input
            **kwargs: Additional validation parameters
            
        Returns:
            Validated value
            
        Raises:
            ValidationError: If validation fails
            
        Validates: Requirement 18.6, Property 32
        """
        try:
            if input_type == InputType.USERNAME:
                return InputValidator.validate_username(value)
            elif input_type == InputType.PASSWORD:
                return InputValidator.validate_password(value)
            elif input_type == InputType.EMAIL:
                return InputValidator.validate_email(value)
            elif input_type == InputType.SYMBOL:
                return InputValidator.validate_symbol(value)
            elif input_type == InputType.NUMERIC:
                return InputValidator.validate_numeric(value, **kwargs)
            elif input_type == InputType.ALPHANUMERIC:
                return InputValidator.validate_alphanumeric(value, **kwargs)
            elif input_type == InputType.TEXT:
                return InputValidator.sanitize_text(value, **kwargs)
            elif input_type == InputType.API_KEY:
                return InputValidator.validate_api_key(value)
            else:
                raise ValidationError(f"Unknown input type: {input_type}")
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Validation error for {input_type}: {e}")
            raise ValidationError(f"Invalid {input_type.value}")
