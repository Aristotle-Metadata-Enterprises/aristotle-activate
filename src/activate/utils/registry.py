import requests
from dataclasses import dataclass
import uuid


@dataclass
class Registry:
    url: str
    pipeline: uuid.UUID = None
    api_token: str = ""

    endpoints = {
        "send_payload": "/api/activate/payload",
        "send_payload_to_pipeline": "/api/activate/pipeline/{self.pipeline}/payload"
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

    def send_payload(self, description, data):
        if self.pipeline:
            url = self.endpoint("send_payload_to_pipeline")
        else:
            url = self.endpoint("send_payload")
        token = self.get_api_token()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {token}"
        }

        payload = {
            "description": description,
            "payload_data": data
        }

        response = requests.post(
            url,
            headers=headers, json=payload, verify=False
        )
        return self.pipeline, response
