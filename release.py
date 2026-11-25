VERSION = "v2"


def dispatch(number, mode):
    """Simulate forwarding a confirmation after the transaction has closed."""
    if mode == "closed":
        return {"id": number, "error": "Confirmation gateway is closed"}, 503
    return {
        "id": number,
        "delivery": {"state": "queued", "reference": f"SE-D{number:05d}"},
    }, 201
