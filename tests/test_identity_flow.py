from trust_call_backend.metrics_registry import MetricsRegistry


def test_metrics_registry_increment_counter():
    m = MetricsRegistry()
    m.inc('my_counter')
    out = m.render()
    assert 'my_counter 1.0' in out


def test_metrics_registry_labels_rendered():
    m = MetricsRegistry()
    m.inc('requests', status='ok')
    rendered = m.render()
    assert 'requests{status="ok"} 1.0' in rendered
