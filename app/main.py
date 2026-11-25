"""Tiny Flask app for the DevOps assessment."""
import os

from flask import Flask, jsonify

app = Flask(__name__)

# Config comes from environment variables, not from code.
GREETING = os.environ.get("GREETING", "Hello, DevOps")


@app.get("/")
def index():
    return GREETING + "\n"


@app.get("/health")
def health():
    # Shallow check: proves the process is up and can answer HTTP.
    # It does NOT check dependencies (this app has none).
    return jsonify(status="ok")
