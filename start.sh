#!/bin/bash

cd "$(dirname "$0")"
source venv/bin/activate
python main.py

read -p "Appuyez sur Entrée pour continuer..."