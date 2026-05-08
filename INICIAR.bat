@echo off
echo ========================================
echo   DaleWeatherBot — Polymarket
echo ========================================
echo.
echo Instalando dependencias...
pip install fastapi uvicorn[standard] httpx pydantic pydantic-settings python-dotenv sqlalchemy[asyncio] aiosqlite websockets python-dateutil py-clob-client -q
echo.
if not exist data mkdir data
echo Iniciando bot em modo PAPER...
echo Dashboard: http://localhost:8000
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
