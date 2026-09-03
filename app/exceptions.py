from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from app.envelope import build_envelope


class OrcaException(Exception):
    def __init__(self, message: str):
        self.message = message


async def orca_exception_handler(request: Request, exc: OrcaException):
    return JSONResponse(
        status_code=400,
        content=build_envelope(errors=[exc.message]),
    )


def _format_validation_errors(errors: list) -> list[str]:
    formatted = []
    for error in errors:
        loc = ".".join(str(l) for l in error["loc"] if l != "body")
        msg = error["msg"]
        formatted.append(f"{loc}: {msg}" if loc else msg)
    return formatted


async def validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=422,
        content=build_envelope(errors=_format_validation_errors(exc.errors())),
    )


async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=build_envelope(errors=_format_validation_errors(exc.errors())),
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=build_envelope(errors=[str(exc.detail)]),
    )


async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=build_envelope(errors=["Internal server error"]),
    )


def register_exception_handlers(app: FastAPI):
    app.add_exception_handler(OrcaException, orca_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
