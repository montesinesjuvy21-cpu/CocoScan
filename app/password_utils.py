"""
Password hashing and security utilities for CocoScan
Uses werkzeug.security for password hashing
"""
from werkzeug.security import generate_password_hash, check_password_hash


def hash_password(password: str) -> str:
    """
    Hash a password using PBKDF2 with SHA256
    
    Args:
        password: Plain text password to hash
    
    Returns:
        Hashed password string safe for database storage
    """
    return generate_password_hash(password, method='pbkdf2:sha256')


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a plain text password against a stored hash
    
    Args:
        password: Plain text password to verify
        password_hash: Stored password hash
    
    Returns:
        True if password matches, False otherwise
    """
    return check_password_hash(password_hash, password)


def is_strong_password(password: str) -> bool:
    """
    Quick check if password meets strength requirements
    (More detailed validation is in validators.py)
    
    Args:
        password: Password to check
    
    Returns:
        True if strong, False otherwise
    """
    return (
        len(password) >= 8 and
        any(c.isupper() for c in password) and
        any(c.islower() for c in password) and
        any(c.isdigit() for c in password) and
        any(c in '!@#$%^&*()_+-=[]{};\':\",./<>?\\|`~' for c in password)
    )
