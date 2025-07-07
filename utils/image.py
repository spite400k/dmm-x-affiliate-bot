import os
import requests
import uuid

TEMP_DIR = "data/temp"

os.makedirs(TEMP_DIR, exist_ok=True)

def download_images(urls: list[str]) -> list[str]:
    paths = []
    for url in urls:
        filename = f"{uuid.uuid4().hex}.jpg"
        path = os.path.join(TEMP_DIR, filename)
        r = requests.get(url)
        with open(path, "wb") as f:
            f.write(r.content)
        paths.append(path)
    return paths
