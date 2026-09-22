"""FastAPI entrypoint discovered from the CodeRepository's top-level api directory."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def hello() -> dict[str, str]:
    return {"message": "Hello, world!"}

