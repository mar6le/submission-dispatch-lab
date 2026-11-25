import os
import re

from flask import Flask, g, request

from observability import configure, emit
from release import VERSION, dispatch
from storage import Submissions

GROUP_PATTERN = re.compile(r"SE-[0-9]{2}")


def create_app():
    app = Flask(__name__)
    submissions = Submissions(os.getenv("SUBMIT_DB", "dispatch.sqlite"))
    mode = os.getenv("DISPATCH_MODE", "ready")
    configure(app, VERSION)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": VERSION}

    @app.get("/submissions/<int:number>")
    def read(number):
        result = submissions.find(number)
        if result is None:
            return {"error": "Submission was not found"}, 404
        return result

    @app.post("/submissions")
    def accept():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return {"error": "Request must contain a JSON object"}, 400
        group, key = payload.get("group_code"), payload.get("submission_key")
        if not isinstance(group, str) or not GROUP_PATTERN.fullmatch(group):
            return {"error": "Group code must match SE-NN"}, 400
        if not isinstance(key, str) or not key.strip() or len(key) > 64:
            return {"error": "Provide a submission key of 1 to 64 characters"}, 400

        g.number, stored_group, created = submissions.save(group, key)
        if stored_group != group:
            return {"error": "Key is registered to another group"}, 409
        if not created:
            return {"id": g.number}, 200
        emit(VERSION, "submission_saved", 201)

        body, status = dispatch(g.number, mode)
        if status == 503:
            emit(VERSION, "confirmation_failed", status)
        elif "delivery" in body:
            emit(VERSION, "confirmation_sent", status)
        return body, status

    return app
