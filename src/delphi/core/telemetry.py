"""OpenTelemetry 集成（可选依赖，未安装时自动降级为 NoOp）"""

from __future__ import annotations

from typing import Any

from loguru import logger

_HAS_OTEL = True
try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except ImportError:
    _HAS_OTEL = False

_initialized = False


# ---------------------------------------------------------------------------
# NoOp 替身：OTel 未安装时使用，保持调用方代码不变
# ---------------------------------------------------------------------------


class _NoOpSpan:
    """什么都不做的 span 替身。"""

    def set_attribute(self, key: str, value: Any) -> None: ...
    def set_status(self, *args: Any, **kwargs: Any) -> None: ...
    def record_exception(self, exception: BaseException) -> None: ...
    def end(self) -> None: ...
    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None: ...


class _NoOpTracer:
    """什么都不做的 tracer 替身。"""

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


class _NoOpMeter:
    """什么都不做的 meter 替身。"""

    def create_histogram(self, name: str, **kwargs: Any) -> Any:
        return type("_NoOpHistogram", (), {"record": lambda self, *a, **kw: None})()

    def create_counter(self, name: str, **kwargs: Any) -> Any:
        return type("_NoOpCounter", (), {"add": lambda self, *a, **kw: None})()


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------


def init_telemetry(service_name: str = "delphi", otlp_endpoint: str = "http://localhost:4317") -> None:
    """初始化 OpenTelemetry TracerProvider 和 MeterProvider。

    如果 OTel SDK 未安装，静默跳过（使用 NoOp 替身）。
    """
    global _initialized  # noqa: PLW0603

    if not _HAS_OTEL:
        logger.info("OpenTelemetry SDK 未安装, 遥测功能已禁用")
        return

    if _initialized:
        logger.debug("OpenTelemetry 已初始化, 跳过重复初始化")
        return

    resource = Resource.create({"service.name": service_name})

    # Traces
    tracer_provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)
    logger.debug("TracerProvider 已配置, endpoint={}", otlp_endpoint)

    # Metrics
    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True))
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    logger.debug("MeterProvider 已配置, endpoint={}", otlp_endpoint)

    _initialized = True
    logger.info("OpenTelemetry 初始化完成, service={}, endpoint={}", service_name, otlp_endpoint)


def get_tracer(name: str) -> Any:
    """获取 tracer 实例。OTel 未安装时返回 NoOp tracer。"""
    if _HAS_OTEL:
        logger.debug("获取 OTel tracer, name={}", name)
        return trace.get_tracer(name)
    logger.debug("OTel 未安装, 返回 NoOp tracer, name={}", name)
    return _NoOpTracer()


def get_meter(name: str) -> Any:
    """获取 meter 实例。OTel 未安装时返回 NoOp meter。"""
    if _HAS_OTEL:
        logger.debug("获取 OTel meter, name={}", name)
        return metrics.get_meter(name)
    logger.debug("OTel 未安装, 返回 NoOp meter, name={}", name)
    return _NoOpMeter()
