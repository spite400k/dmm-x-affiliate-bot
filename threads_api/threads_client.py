# threads_api/threads_client.py
import requests

class ThreadsClient:
    def __init__(self, access_token: str, user_id: str):
        self.access_token = access_token
        self.user_id = user_id
        self.base_url = f"https://graph.threads.net/v1.0/{user_id}/threads"

    def post_thread(self, text: str, image_url: str = None):
        payload = {"text": text}
        if image_url:
            payload["image_url"] = image_url

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        response = requests.post(self.base_url, json=payload, headers=headers)

        if response.status_code == 200:
            print("✅ Threads投稿成功:", response.json())
            return response.json()
        else:
            print("❌ Threads投稿失敗:", response.status_code, response.text)
            return None
