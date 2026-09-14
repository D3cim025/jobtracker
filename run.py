import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("JOBTRACKER_HOST", "127.0.0.1"),
        port=int(os.environ.get("JOBTRACKER_PORT", "5000")),
        debug=os.environ.get("JOBTRACKER_DEBUG") == "1",
    )

