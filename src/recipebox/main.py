from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from recipebox.database import close_pool, init_pool

from .api import auth, health, recipes, tags
from .domain.errors import ConflictError, ForbiddenError, NotFoundError, RecipeImportError, UnauthorizedError


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(recipes.router)
app.include_router(tags.router)


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(UnauthorizedError)
async def unauthorized_handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.exception_handler(ForbiddenError)
async def forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(RecipeImportError)
async def import_error_handler(request: Request, exc: RecipeImportError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})
