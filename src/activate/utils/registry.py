import requests
from dataclasses import dataclass
import uuid


@dataclass
class Registry:
    url: str
    plan: uuid.UUID
    api_token: str = ""

    endpoints = {
        "send_payload": "/api/activate/plan/{self.plan}/activate"
    }

    def get_api_token(self):
        if token := self.api_token:
            return token
        return ""

    def send_payload(self, data):
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.get_api_token()
        }

        response = requests.post(self.url, headers=headers, json=data)

        return response
