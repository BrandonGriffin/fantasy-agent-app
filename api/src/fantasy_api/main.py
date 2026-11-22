from fastapi import FastAPI

from fantasy_api.best_ball.routes import router as best_ball_router
from fantasy_api.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()
    app = FastAPI(title="Fantasy Agent API")
    app.state.settings = settings

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(best_ball_router)

    return app
