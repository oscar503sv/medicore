"""Entry point: uvicorn medicore.presentation.main:app"""

from medicore.presentation.app import create_app

app = create_app()
