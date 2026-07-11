import pytest

from app.validators import ValidationError, validate_age, validate_email_format, validate_name, validate_signup_data


def test_validate_name_rejects_numbers_and_special_characters():
    with pytest.raises(ValidationError, match="letters"):
        validate_name("Juan123", "First Name")

    with pytest.raises(ValidationError, match="letters"):
        validate_name("Juan@Doe", "First Name")


def test_validate_age_limits_to_18_to_99():
    assert validate_age("18") == 18
    assert validate_age("99") == 99

    with pytest.raises(ValidationError, match="between 18 and 99"):
        validate_age("17")

    with pytest.raises(ValidationError, match="between 18 and 99"):
        validate_age("100")


def test_validate_email_format_requires_a_valid_address():
    assert validate_email_format("user@example.com") == "user@example.com"

    with pytest.raises(ValidationError, match="Invalid email"):
        validate_email_format("not-an-email")


def test_validate_signup_data_uses_barangay_and_fixed_location_fields():
    form_data = {
        "first_name": "Maria",
        "last_name": "Garcia",
        "email": "maria@example.com",
        "age": "28",
        "barangay": "San Cristobal",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }

    validated = validate_signup_data(form_data, "farmer")

    assert validated["barangay"] == "San Cristobal"
    assert validated["municipality"] == "San Pablo City"
    assert validated["province"] == "Laguna"
    assert "address" not in validated
