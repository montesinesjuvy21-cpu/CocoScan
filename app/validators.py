"""
Input validation utilities for CocoScan application
Handles: email, password strength, required fields, age validation
"""
import re
from email_validator import validate_email, EmailNotValidError


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


def validate_email_format(email: str) -> str:
    """
    Validate email format using email-validator
    Returns: normalized email
    Raises: ValidationError if invalid
    """
    try:
        valid = validate_email(email.strip())
        return valid.email
    except EmailNotValidError as e:
        raise ValidationError(f"Invalid email format: {str(e)}")


def validate_password_strength(password: str) -> bool:
    """
    Enforce strong password requirements:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    - At least 1 special character
    
    Returns: True if valid
    Raises: ValidationError with specific requirement details
    """
    if not password or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long")
    
    if not re.search(r'[A-Z]', password):
        raise ValidationError("Password must contain at least one uppercase letter")
    
    if not re.search(r'[a-z]', password):
        raise ValidationError("Password must contain at least one lowercase letter")
    
    if not re.search(r'\d', password):
        raise ValidationError("Password must contain at least one digit (0-9)")
    
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', password):
        raise ValidationError("Password must contain at least one special character (!@#$%^&*)")
    
    return True


def validate_name(name: str, field_name: str) -> str:
    """
    Validate name fields (first, last, middle)
    - Strip whitespace
    - Check minimum length (2 characters)
    - Allow letters, hyphens, and spaces only
    
    Returns: cleaned name
    Raises: ValidationError if invalid
    """
    cleaned = name.strip() if name else ""
    
    if not cleaned or len(cleaned) < 2:
        raise ValidationError(f"{field_name} must be at least 2 characters long")
    
    if not re.match(r"^[a-zA-Z\s\-']+$", cleaned):
        raise ValidationError(f"{field_name} can only contain letters, spaces, hyphens, and apostrophes")
    
    return cleaned


def validate_age(age_str: str) -> int:
    """
    Validate and convert age to integer
    - Must be between 18 and 120
    
    Returns: age as integer
    Raises: ValidationError if invalid
    """
    try:
        age = int(age_str) if age_str else 0
    except (ValueError, TypeError):
        raise ValidationError("Age must be a valid number")
    
    if age < 18 or age > 120:
        raise ValidationError("Age must be between 18 and 120")
    
    return age


def validate_address(address: str) -> str:
    """
    Validate address field
    - Check minimum length
    - Strip whitespace
    
    Returns: cleaned address
    Raises: ValidationError if invalid
    """
    cleaned = address.strip() if address else ""
    
    if not cleaned or len(cleaned) < 5:
        raise ValidationError("Address must be at least 5 characters long")
    
    return cleaned


def validate_required_field(value: str, field_name: str) -> str:
    """
    Validate that a required field is not empty
    
    Returns: cleaned value
    Raises: ValidationError if empty
    """
    cleaned = value.strip() if value else ""
    
    if not cleaned:
        raise ValidationError(f"{field_name} is required")
    
    return cleaned


def validate_signup_data(form_data: dict, role: str) -> dict:
    """
    Comprehensive validation of signup form data
    Returns: cleaned and validated data
    Raises: ValidationError with first encountered error
    """
    errors = []
    
    try:
        # Basic personal information
        first_name = validate_name(form_data.get('first_name', ''), "First Name")
        last_name = validate_name(form_data.get('last_name', ''), "Last Name")
        email = validate_email_format(form_data.get('email', ''))
        age = validate_age(form_data.get('age', ''))
        address = validate_address(form_data.get('address', ''))
        
        # Optional fields
        middle_name = form_data.get('middle_name', '').strip() or None
        if middle_name:
            middle_name = validate_name(middle_name, "Middle Name")
        
        extension_name = form_data.get('extension_name', '').strip() or None
        
        # Password validation
        password = form_data.get('password', '')
        confirm_password = form_data.get('confirm_password', '')
        
        if password != confirm_password:
            raise ValidationError("Passwords do not match")
        
        validate_password_strength(password)
        
        # Role-specific validation
        if role == 'farmer':
            farmer_barangay = validate_required_field(
                form_data.get('farmer_barangay', ''), 
                "Barangay"
            )
            farm_size = form_data.get('farm_size', '').strip() or None
            farm_type = form_data.get('farm_type', '').strip() or None
            
            return {
                'first_name': first_name,
                'middle_name': middle_name,
                'last_name': last_name,
                'extension_name': extension_name,
                'age': age,
                'address': address,
                'email': email,
                'password': password,
                'role': role,
                'farmer_barangay': farmer_barangay,
                'farm_size': farm_size,
                'farm_type': farm_type,
            }
        
        elif role == 'lgu':
            lgu_agency = validate_required_field(
                form_data.get('lgu_agency', ''),
                "Agency/Office"
            )
            lgu_position = validate_required_field(
                form_data.get('lgu_position', ''),
                "Position"
            )
            lgu_employee_id = validate_required_field(
                form_data.get('lgu_employee_id', ''),
                "Employee ID"
            )
            lgu_jurisdiction = validate_required_field(
                form_data.get('lgu_jurisdiction', ''),
                "Jurisdiction"
            )
            lgu_office_email = form_data.get('lgu_office_email', '').strip() or None
            if lgu_office_email:
                lgu_office_email = validate_email_format(lgu_office_email)
            
            return {
                'first_name': first_name,
                'middle_name': middle_name,
                'last_name': last_name,
                'extension_name': extension_name,
                'age': age,
                'address': address,
                'email': email,
                'password': password,
                'role': role,
                'lgu_agency': lgu_agency,
                'lgu_position': lgu_position,
                'lgu_employee_id': lgu_employee_id,
                'lgu_office_email': lgu_office_email,
                'lgu_jurisdiction': lgu_jurisdiction,
            }
        
        elif role == 'agri_expert':
            agri_office_name = validate_required_field(
                form_data.get('agri_office_name', ''),
                "Office Name"
            )
            agri_position = validate_required_field(
                form_data.get('agri_position', ''),
                "Position"
            )
            agri_employee_id = validate_required_field(
                form_data.get('agri_employee_id', ''),
                "Employee ID"
            )
            agri_jurisdiction = validate_required_field(
                form_data.get('agri_jurisdiction', ''),
                "Jurisdiction"
            )
            agri_office_email = form_data.get('agri_office_email', '').strip() or None
            if agri_office_email:
                agri_office_email = validate_email_format(agri_office_email)
            
            return {
                'first_name': first_name,
                'middle_name': middle_name,
                'last_name': last_name,
                'extension_name': extension_name,
                'age': age,
                'address': address,
                'email': email,
                'password': password,
                'role': role,
                'agri_office_name': agri_office_name,
                'agri_position': agri_position,
                'agri_employee_id': agri_employee_id,
                'agri_office_email': agri_office_email,
                'agri_jurisdiction': agri_jurisdiction,
            }
        
        else:
            raise ValidationError("Invalid role selected")
    
    except ValidationError:
        raise


def validate_duplicate_email(supabase_client, email: str) -> bool:
    """
    Check if email already exists in users table
    Returns: True if email exists, False otherwise
    """
    try:
        response = supabase_client.table("users").select("id").eq("email", email).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error checking duplicate email: {str(e)}")
        return False


def validate_login_credentials(supabase_client, email: str, password: str) -> dict:
    """
    Validate login credentials securely
    - Check if email exists in database
    - Verify password against stored hash
    - Return user data if successful
    
    IMPORTANT: Returns generic error message for both "account not found" 
    and "password incorrect" to prevent email enumeration attacks
    
    Args:
        supabase_client: Supabase client instance
        email: User's email address
        password: User's plain text password
    
    Returns:
        Dictionary with user data if credentials are valid
        
    Raises:
        ValidationError: If credentials don't match any account
    """
    from app.password_utils import verify_password
    
    if not email or not password:
        raise ValidationError("Email and password are required")
    
    try:
        # Normalize email
        email_normalized = email.strip().lower()
        
        # Query database for user with this email
        response = supabase_client.table("users").select(
            "id, first_name, last_name, email, password_hash, role, status"
        ).eq("email", email_normalized).execute()
        
        # Check if user exists
        if not response.data or len(response.data) == 0:
            # SECURITY: Don't reveal if email exists or not
            raise ValidationError("Invalid email or password. If you don't have an account, please sign up.")
        
        user = response.data[0]
        
        # Verify password against stored hash
        if not verify_password(password, user['password_hash']):
            # SECURITY: Same generic error message as above
            raise ValidationError("Invalid email or password. If you don't have an account, please sign up.")
        
        # Check if account is approved (optional - adjust based on your workflow)
        if user['status'] == "Rejected":
            raise ValidationError("Your account has been rejected. Please contact support.")
        
        # Password is correct - return user data (without password_hash)
        return {
            'id': user['id'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'email': user['email'],
            'role': user['role'],
            'status': user['status']
        }
    
    except ValidationError:
        raise
    except Exception as e:
        # Log the actual error but return generic message to user
        print(f"Login validation error: {str(e)}")
        raise ValidationError("Invalid email or password. If you don't have an account, please sign up.")


def validate_login_form(form_data: dict) -> tuple:
    """
    Validate login form inputs before credential check
    
    Args:
        form_data: Form data dictionary
    
    Returns:
        Tuple of (email, password)
        
    Raises:
        ValidationError if inputs are invalid
    """
    email = form_data.get('email', '').strip()
    password = form_data.get('password', '')
    
    if not email:
        raise ValidationError("Email address is required")
    
    if not password:
        raise ValidationError("Password is required")
    
    # Validate email format
    try:
        email = validate_email_format(email)
    except ValidationError:
        # SECURITY: Don't reveal format error for login (could be enumeration vector)
        raise ValidationError("Invalid email or password")
    
    return email, password
