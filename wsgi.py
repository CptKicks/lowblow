# wsgi.py
import sys
import os

print("Current directory:", os.getcwd())
print("Files in directory:", os.listdir())
print("Python path:", sys.path)

try:
    from paste import app

    print("Successfully imported app from paste")
except ImportError as e:
    print(f"Error importing from paste: {e}")

    try:
        import paste

        print(f"Successfully imported paste module: {paste}")
    except ImportError as e:
        print(f"Error importing paste module: {e}")

# Export the app variable
app = app