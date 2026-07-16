from fastapi import FastAPI

app = FastAPI(title="LabForge backend")


@app.get("/health")
def health() -> dict[str, str]:
    """Report backend application availability only."""
    return {"status": "available"}
