from app import create_app

app = create_app()

if __name__ == "__main__":
    print("")
    print("  Container Planning & Schedule — J&J")
    print("  ─────────────────────────────────────")
    print("  Open your browser and go to:")
    print("  http://localhost:5000")
    print("")
    print("  Press CTRL+C to stop the server.")
    print("")
    app.run(host="127.0.0.1", port=5000, debug=True)
