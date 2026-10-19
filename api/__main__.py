"""python -m api: serve the app on this laptop only. Put it behind HTTPS (a reverse
proxy or a host) before letting other computers in, or passwords cross the network
unencrypted."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.app:app", host="127.0.0.1", port=8000)
