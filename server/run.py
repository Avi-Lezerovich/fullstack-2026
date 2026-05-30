"""Server entrypoint: `python run.py` → http://localhost:5001"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))  # 5001 avoids the macOS AirPlay :5000 clash
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
