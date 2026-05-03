from trust_call_backend.metrics_registry import MetricsRegistry


def test_metrics_registry_increment_counter():
    metrics = MetricsRegistry()
    metrics.inc("my_counter")
    rendered = metrics.render()
    assert "my_counter 1.0" in rendered


def test_metrics_registry_labeled_counter():
    metrics = MetricsRegistry()
    metrics.inc("requests_total", status="ok")
    rendered = metrics.render()
    assert 'requests_total{status="ok"} 1.0' in rendered
