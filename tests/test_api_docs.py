"""The OpenAPI document that /docs, /redoc and partners' client generators read (no OCR model needed)."""

from app import pipeline
from app.main import app


def test_openapi_documents_extract():
    spec = app.openapi()
    op = spec["paths"]["/api/extract"]["post"]
    assert set(op["responses"]) >= {"200", "413", "415", "422", "503"}
    assert op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/ExtractResponse")
    params = {p["name"]: p for p in op["parameters"]}
    assert all(params[name].get("description") for name in ("document", "include_image", "crop", "mode", "engine"))
    # every document the API accepts is listed in the description table
    assert all(f"`{doc}`" in spec["info"]["description"] for doc in pipeline.DOCUMENT_CHOICES)
    assert "/" not in spec["paths"]  # the web page is not part of the API
