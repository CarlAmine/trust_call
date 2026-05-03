import asyncio

from trust_call_backend.service_clients import (
    fetch_distilbert_prediction,
    fetch_rawnet_prediction,
)


class _Resp:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _ClientOK:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json, timeout):
        if 'rawnet' in url:
            return _Resp(payload={'spoof_probability_percent': 42.0})
        return _Resp(payload={'semantic_score': 0.7, 'label': 'suspicious'})


class _ClientFail(_ClientOK):
    async def post(self, url, json, timeout):
        raise RuntimeError('down')


def test_rawnet_success(monkeypatch):
    monkeypatch.setattr('trust_call_backend.service_clients.httpx.AsyncClient', _ClientOK)
    assert asyncio.run(fetch_rawnet_prediction('AAAA', 'http://rawnet/predict')) == 42.0


def test_rawnet_failure_returns_zero(monkeypatch):
    monkeypatch.setattr('trust_call_backend.service_clients.httpx.AsyncClient', _ClientFail)
    assert asyncio.run(fetch_rawnet_prediction('AAAA', 'http://rawnet/predict')) == 0.0


def test_distilbert_empty_text_short_circuit():
    result = asyncio.run(fetch_distilbert_prediction('', 'http://distilbert/predict'))
    assert result['label'] == 'insufficient_text'


def test_distilbert_failure_returns_fallback(monkeypatch):
    monkeypatch.setattr('trust_call_backend.service_clients.httpx.AsyncClient', _ClientFail)
    result = asyncio.run(fetch_distilbert_prediction('hello', 'http://distilbert/predict'))
    assert result['label'] == 'semantic_unavailable'
