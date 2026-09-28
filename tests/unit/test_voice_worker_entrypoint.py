"""The LiveKit job callback must survive child-process serialization."""

import pickle
from types import SimpleNamespace
from uuid import uuid4

from livekit import rtc
from voice_fleet_worker.worker import (
    is_expected_sip_participant,
    response_latency,
    voice_session,
)


def test_voice_session_callback_is_importable_by_child_process() -> None:
    assert voice_session.__module__ == "voice_fleet_worker.worker"
    assert pickle.loads(pickle.dumps(voice_session)) is voice_session


def test_latency_prefers_speech_end_and_falls_back_to_final_transcript() -> None:
    assert response_latency({"e2e_latency": 0.42, "started_speaking_at": 10.5}, 10.0) == (
        "e2e_latency_ms",
        420,
    )
    assert response_latency({"started_speaking_at": 10.5}, 10.0) == (
        "stt_final_to_audio_start_ms",
        500,
    )
    assert response_latency({"started_speaking_at": 9.5}, 10.0) is None


def test_inbound_sip_participant_must_match_number_trunk_and_rule() -> None:
    expected = ("ST-one", "SDR-one", "+15551234567")
    session_id = uuid4()
    participant = SimpleNamespace(
        kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP,
        identity="sip-caller",
        attributes={
            "sip.trunkID": expected[0],
            "sip.ruleID": expected[1],
            "sip.trunkPhoneNumber": expected[2],
        },
    )
    assert is_expected_sip_participant(participant, session_id, "inbound", expected)
    participant.attributes["sip.ruleID"] = "SDR-other"
    assert not is_expected_sip_participant(participant, session_id, "inbound", expected)
    participant.attributes["sip.ruleID"] = expected[1]
    participant.kind = rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD
    assert not is_expected_sip_participant(participant, session_id, "inbound", expected)
