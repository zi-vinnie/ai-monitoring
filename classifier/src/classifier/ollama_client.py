import requests


def classify_image(
    ollama_url: str,
    model: str,
    prompt: str,
    image_b64: str,
    response_format: dict,
    timeout: float = 120.0,
) -> str:
    """Send one screenshot to a local Ollama vision model; return its raw text.

    Uses ``/api/generate`` with the PNG attached and structured-output
    ``format`` so the model is constrained to a valid label. ``temperature`` 0
    keeps labelling deterministic. Raises ``requests`` errors on HTTP/transport
    failure so the caller can log and skip that one image.
    """
    response = requests.post(
        f"{ollama_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "images": [image_b64],
            "format": response_format,
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("response", "")
