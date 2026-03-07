import os
import time

UPLOAD_FOLDER = "knowledge/uploads/original_files"

MAX_AGE = 30 * 24 * 3600  # 30 hari

now = time.time()

for file in os.listdir(UPLOAD_FOLDER):

    path = os.path.join(UPLOAD_FOLDER, file)

    if os.path.isfile(path):

        age = now - os.path.getmtime(path)

        if age > MAX_AGE:

            os.remove(path)

            print("Deleted:", file)