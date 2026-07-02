#!/usr/bin/env bash
# Install system dependencies for Image Intelligence Engine (requires sudo).
set -euo pipefail

if ! command -v apt-get &>/dev/null; then
    echo "apt-get not found — install tesseract-ocr and exiftool manually."
    exit 1
fi

sudo apt-get update -qq
sudo apt-get install -y -qq \
    tesseract-ocr \
    libtesseract-dev \
    libimage-exiftool-perl

echo "System image intelligence dependencies installed."
tesseract --version | head -1
exiftool -ver
