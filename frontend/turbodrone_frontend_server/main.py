import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import importlib.resources

def main():
    app = FastAPI()

    # Path to the static files
    try:
        static_files_dir = str(importlib.resources.files('turbodrone_frontend_server').joinpath('dist'))
    except (ImportError, AttributeError):
        # Fallback for older python
        import pkg_resources
        static_files_dir = pkg_resources.resource_filename('turbodrone_frontend_server', 'dist')


    app.mount("/assets", StaticFiles(directory=os.path.join(static_files_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def read_index(full_path: str):
        """
        Serve the index.html for any path that is not a static file.
        This is needed for client-side routing.
        """
        return FileResponse(os.path.join(static_files_dir, 'index.html'))

    print("Starting frontend server on http://localhost:3000")
    uvicorn.run(app, host="0.0.0.0", port=3000)

if __name__ == "__main__":
    main()
