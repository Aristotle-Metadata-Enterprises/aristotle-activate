import requests
from dataclasses import dataclass
import uuid


@dataclass
class Registry:
    url: str
    # plan: uuid.UUID
    api_token: str = ""

    endpoints = {
        "send_payload": "/api/activate/payload"
    }

    def endpoint(self, endpoint):
        base = self.url.rstrip("/")
        endpoint = self.endpoints[endpoint].format(self=self).lstrip("/")
        url = f"{base}/{endpoint}"
        return url

    def get_api_token(self):
        if token := self.api_token:
            return token
        return ""

    def send_payload(self, data):
        url = self.endpoint("send_payload")
        token = self.get_api_token()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {token}"
        }

        response = requests.post(
            url,
            headers=headers, json=data, verify=False
        )
        return response
