"""Gemini 호출 로직(모델 순서, 재시도, 오류 처리) 테스트 - 실제 API 대신 가짜 클라이언트 사용."""
import json

import pytest

import core.gemini_solver as gs
from server.main import friendly_ai_error

GOOD = json.dumps({"steps": ["x"], "final_answer": "① 1/8", "figure_annotations": []})


class FakeError(Exception):
    def __init__(self, code):
        super().__init__(f"{code} error")
        self.code = code


class FakeModels:
    def __init__(self, script):
        self.script = script  # model -> list of results (예외 코드 또는 "ok")
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append((model, config is not None))
        outcome = self.script[model].pop(0)
        if outcome == "ok":
            return type("Resp", (), {"text": GOOD})()
        raise FakeError(outcome)


def run(monkeypatch, script, models):
    fake = FakeModels(script)
    monkeypatch.setattr(gs.genai, "Client", lambda api_key: type("C", (), {"models": fake})())
    monkeypatch.setattr(gs.time, "sleep", lambda s: None)
    monkeypatch.setenv("GEMINI_MODELS", ",".join(models))
    return gs.solve_problem_with_gemini(image_bytes=b"x", mime_type="image/jpeg", api_key="k"), fake.calls


def test_overloaded_model_falls_through_without_retry(monkeypatch):
    res, calls = run(monkeypatch, {"gemini-3.8-flash": [503], "gemini-3.7-flash": ["ok"]},
                     ["gemini-3.8-flash", "gemini-3.7-flash"])
    assert res["final_answer"] == "① 1/8" and res["used_model"] == "Gemini 3.7 Flash"
    assert [c[0] for c in calls] == ["gemini-3.8-flash", "gemini-3.7-flash"]  # 다른 모델이 남았으면 재시도 없이 바로


def test_quota_exhausted_is_not_retried(monkeypatch):
    res, calls = run(monkeypatch, {"gemini-3.8-flash": [429]}, ["gemini-3.8-flash"])
    assert res.get("error") and len(calls) == 1


def test_last_model_gets_one_retry_on_overload(monkeypatch):
    res, calls = run(monkeypatch, {"gemini-3.5-flash-lite": [503, "ok"]}, ["gemini-3.5-flash-lite"])
    assert res["used_model"] == "Gemini 3.5 Flash-Lite" and len(calls) == 2


def test_json_config_rejected_retries_without_config(monkeypatch):
    res, calls = run(monkeypatch, {"m": [400, "ok"]}, ["m"])
    assert not res.get("error") and calls == [("m", True), ("m", False)]


@pytest.mark.parametrize("raw, expected", [
    ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"),
    ("models/gemini-3.8-flash", "Gemini 3.8 Flash"),
    ("gemini-9-ultra", "gemini-9-ultra"),
])
def test_format_model_name(raw, expected):
    assert gs.format_model_name(raw) == expected


def test_model_discovery_skips_non_solver_models():
    names = ["gemini-3.8-flash-tts", "gemini-3.1-pro-preview", "gemini-3.5-flash-lite", "gemini-3.8-flash",
             "gemini-3-pro-image", "gemini-3.7-flash", "gemini-2.5-flash"]
    usable = [n for n in names if not any(w in n for w in gs._NON_SOLVER_MODEL_WORDS)]
    assert sorted(usable, key=gs._model_priority)[:3] == ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-2.5-flash"]


@pytest.mark.parametrize("detail, phrase", [
    ("429 RESOURCE_EXHAUSTED quota", "사용량"),
    ("503 UNAVAILABLE high demand", "잠시 후"),
    ("400 API key not valid", "키 설정"),
    ("something else", "실패"),
])
def test_friendly_ai_error(detail, phrase):
    assert phrase in friendly_ai_error(detail)
