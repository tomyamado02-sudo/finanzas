#!/bin/bash
# Doble clic en este archivo para abrir InvestSim en el navegador

cd "$(dirname "$0")"

echo "Instalando dependencias si faltan..."
pip3 install -q -r requirements.txt 2>/dev/null

echo "Abriendo InvestSim en el navegador..."
sleep 1
open http://localhost:8000

echo "Iniciando servidor... (cerrá esta ventana para apagar la app)"
python3 web_app.py
