from datetime import date

import pytest

try:
    from registry_patient_connect import OR_AFTER_HOURS, route_case_to_or
except ImportError as exc:  # pragma: no cover - environment dependency
    pytest.skip(f"registry_patient_connect unavailable: {exc}", allow_module_level=True)


def test_borrow_same_department_daytime():
    or_key, meta = route_case_to_or(
        day_idx=date(2024, 7, 16),  # Tuesday
        time_str="10:00",
        doctor_name="นพ.สุริยา คุณาชน",
    )
    assert or_key == "OR6"
    assert meta["borrowed"] is True


def test_after_hours_tf_bucket():
    or_key, meta = route_case_to_or(
        day_idx=date(2024, 7, 17),  # Wednesday
        time_str="TF",
        doctor_name="นพ.สุริยา คุณาชน",
    )
    assert or_key == OR_AFTER_HOURS
    assert meta["borrowed"] is False


def test_after_hours_time_bucket():
    or_key, meta = route_case_to_or(
        day_idx=date(2024, 7, 16),  # Tuesday
        time_str="17:00",
        doctor_name="นพ.ธนวัฒน์ พันธุ์พรหม",
    )
    assert or_key == OR_AFTER_HOURS
    assert meta["borrowed"] is False


def test_obgyn_does_not_borrow_daytime():
    or_key, meta = route_case_to_or(
        day_idx=date(2024, 7, 18),  # Thursday
        time_str="13:30",
        doctor_name="พญ.วิรัชกรกศณท์ ณัชชาวัชฌะคุปต์",
    )
    assert or_key is None
    assert meta["borrowed"] is False
