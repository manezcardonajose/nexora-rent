@echo off
title Gestor de Alquiler Vacacional - PRODUCCION
color 0E

:: Configurar codificación UTF-8 para caracteres especiales
chcp 65001 >nul

:: Limpiar pantalla
cls

echo ========================================
echo   GESTOR DE ALQUILER VACACIONAL
echo         MODO PRODUCCIÓN
echo ========================================
echo.

:: Configurar variables de entorno
set FLASK_ENV=production
set FLASK_DEBUG=0
set PYTHONUNBUFFERED=1

:: Intentar activar Conda desde diferentes ubicaciones
set "CONDA_PATH=%UserProfile%\miniconda3"
set "CONDA_PATH_ALT=%LocalAppData%\Continuum\miniconda3"

if exist "%CONDA_PATH%\Scripts\conda.exe" (
    call "%CONDA_PATH%\Scripts\activate.bat" alquiler_env
) else if exist "%CONDA_PATH_ALT%\Scripts\conda.exe" (
    call "%CONDA_PATH_ALT%\Scripts\activate.bat" alquiler_env
) else (
    echo [ADVERTENCIA] Conda no encontrado en rutas típicas.
    echo Intentando usar comando 'conda' desde PATH...
    call conda activate alquiler_env 2>nul
)

:: Verificar si la activación funcionó
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] No se pudo activar Python. Asegúrate de tener Conda instalado.
    pause
    exit /b 1
)

echo [OK] Entorno Python activado
echo.

:: Ir a la carpeta del proyecto
cd /d "C:\Users\jmpep\source\repos\alquiler vacacional"
if %errorlevel% neq 0 (
    echo [ERROR] No se encuentra la carpeta del proyecto
    pause
    exit /b 1
)

echo [OK] Directorio: %CD%
echo.

:: Verificar que waitress está instalado
python -c "import waitress" 2>nul
if %errorlevel% neq 0 (
    echo Instalando waitress...
    pip install waitress
)

:: Mostrar IP para acceso móvil
echo ========================================
echo   🌐 ACCEDE DESDE TU MÓVIL
echo ========================================
echo.
echo En la MISMA RED WIFI, usa alguna de estas IPs:
ipconfig | findstr IPv4
echo.
echo Ejemplo: http://192.168.8.5:5000
echo.

:: Ejecutar la aplicación usando el módulo waitress
echo ========================================
echo   🚀 INICIANDO SERVIDOR WAITRESS
echo ========================================
echo.
echo   📱 Servidor disponible en:
echo      • Local:    http://127.0.0.1:5000
echo      • Red local: Usa la IP de arriba
echo.
echo   ⏹️  Para detener: Ctrl+C
echo ========================================
echo.

:: 🔴 CAMBIO IMPORTANTE: Usar python -m waitress en lugar de waitress-serve
python -m waitress --host=0.0.0.0 --port=5000 --threads=4 app:app

pause
