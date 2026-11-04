"""CLI entry: uvicorn stock_platform_workbench.app:create_app."""

from __future__ import annotations


def main() -> None:
    # Load local/.env before the app reads os.environ (bat is optional).
    from stock_platform_research.settings import get_settings

    get_settings()

    import uvicorn

    uvicorn.run(
        "stock_platform_workbench.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=3018,
        reload=False,
    )


if __name__ == "__main__":
    main()
