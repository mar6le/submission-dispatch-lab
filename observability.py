import json
from datetime import datetime, timezone
from uuid import uuid4

from flask import Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, generate_latest


def emit(version, event, status):
    row = {
        "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "version": version, "request_id": g.request_id, "event": event, "status": status,
    }
    if g.number is not None:
        row["submission_id"] = g.number
    print(json.dumps(row, separators=(",", ":")), flush=True)


def configure(app, version):
    registry = CollectorRegistry()
    counts = Counter(
        "submission_responses_total", "Completed attempts to submit work",
        ("version", "status"), registry=registry,
    )

    @app.before_request
    def assign_context():
        g.request_id = uuid4().hex
        g.number = None

    @app.after_request
    def trace_response(response):
        response.headers["X-Request-Id"] = g.request_id
        if request.endpoint == "accept" and request.method == "POST":
            counts.labels(version, str(response.status_code)).inc()
            emit(version, "submission_response", response.status_code)
        return response

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(registry), content_type=CONTENT_TYPE_LATEST)
