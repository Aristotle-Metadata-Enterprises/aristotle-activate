import requests
from dataclasses import dataclass
import uuid
import json


MAX_ITEMS_PER_PAYLOAD = 150
MAX_PAYLOAD_SIZE_IN_BYTES = 2 * 1024 * 1024  # 2MB


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

    def send_payload(self, data):
        if self.pipeline:
            url = self.endpoint("send_payload_to_pipeline")
        else:
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
        return self.pipeline, response

    def send_as_chunked_payloads(self, scanner):

        send_order = [
            'datatype',
            'valuedomain',
            'distribution',
            'dataset',
        ]

        metadata = scanner.metadata_as_ordered_dict()

        for md_type in send_order:
            for order, ordered_sets in metadata.get(md_type,{}).items():
                for chunk_number, items in self.create_metadata_for_payload(ordered_sets):
                    json_data = {
                        "description": f"{md_type}.order-{order}.chunk-{chunk_number}.json",
                        "payload_data": {
                            md_type: items
                        },
                    }
                    response = None, None
                    self.pipeline, response = self.send_payload(json_data)
                    yield self.pipeline, response

    def create_metadata_for_payload(self, metadata_set):
        items = []

        i = 0
        total_items_size = 0
        chunks = 0
        for item in metadata_set:
            item_size = len(json.dumps(item).encode('utf-8'))
            payload_too_big = (
                (total_items_size + item_size > MAX_PAYLOAD_SIZE_IN_BYTES) or
                (i >= MAX_ITEMS_PER_PAYLOAD)
            )
            if payload_too_big:
                yield chunks, items
                items = []
                total_items_size = 0
                i = 0
                chunks += 1
            else:
                items.append(item)
                total_items_size += item_size
                i += 1

        yield chunks, items