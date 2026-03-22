from app.core.config import Settings


def _settings(**overrides) -> Settings:
    defaults = {
        "discord_bot_token": "token",
        "dispatcher_alert_on_contact_issue": False,
        "dispatcher_alert_channel_id": None,
        "parts_alert_on_contact_issue": False,
        "parts_alert_channel_id": None,
        "workflow_write_assignment": True,
        "workflow_write_sr_note": True,
        "bluefolder_timeout_seconds": 60,
        "assignment_cache_ttl_seconds": 120,
        "workflow_assignment_lookup_days_before": 0,
        "workflow_assignment_lookup_days_after": 0,
        "waiver_base_url": None,
        "waiver_sr_param": "sr",
        "waiver_name_param": "name",
        "waiver_first_name_param": "first_name",
        "waiver_last_name_param": "last_name",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_validation_errors_require_alert_channel_when_dispatch_alerts_enabled():
    settings = _settings(
        dispatcher_alert_on_contact_issue=True,
        dispatcher_alert_channel_id=None,
    )

    errors = settings.validation_errors()

    assert any("DISPATCHER_ALERT_CHANNEL_ID" in error for error in errors)


def test_validation_errors_reject_all_workflow_targets_disabled():
    settings = _settings(
        workflow_write_assignment=False,
        workflow_write_sr_note=False,
    )

    errors = settings.validation_errors()

    assert any("workflow write target" in error.lower() for error in errors)


def test_validation_errors_reject_non_positive_timeout():
    settings = _settings(bluefolder_timeout_seconds=0)

    errors = settings.validation_errors()

    assert "BLUEFOLDER_TIMEOUT_SECONDS must be greater than 0 when set." in errors


def test_validation_errors_reject_blank_waiver_param_when_base_url_set():
    settings = _settings(
        waiver_base_url="https://example.com/waiver",
        waiver_sr_param="",
    )

    errors = settings.validation_errors()

    assert "WAIVER_SR_PARAM cannot be empty when WAIVER_BASE_URL is set." in errors


def test_validate_or_raise_passes_for_valid_settings():
    settings = _settings()

    settings.validate_or_raise()
