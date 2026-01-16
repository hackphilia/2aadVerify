#!/bin/bash
# Install required libraries
pip install --upgrade pip
pip install python-telegram-bot[job-queue] requests GitPython --user

# Run the Member Manager
python3 main.py
