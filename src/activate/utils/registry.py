import requests
from dataclasses import dataclass
import uuid
import json


MAX_ITEMS_PER_PAYLOAD = 75
MAX_PAYLOAD_SIZE_IN_BYTES = 2 * 1024 * 1024  # 2MB


@dataclass
class Registry:
    url: str = None
    pipeline: uuid.UUID = None
    api_token: str = ""
    disable_ssl_verification: bool = False
    items_per_chunk: int = MAX_ITEMS_PER_PAYLOAD
    dry_run: bool = False

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
        if not self.url:
            self.url = "activate://dry-run.example.com"
            self.dry_run = True

        if self.pipeline:
            url = self.endpoint("send_payload_to_pipeline")
        else:
            url = self.endpoint("send_payload")
        token = self.get_api_token()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {token}"
        }

        verify = not self.disable_ssl_verification
        if self.dry_run:
            response = requests.models.Response()
            response.status_code = 201
            response._content = b'Dry run - not sent'
            response.url = url
            return response
        try:
            response = requests.post(
                url,
                headers=headers, json=data, verify=verify
            )
        except Exception as e:
            # Return a mock response
            response = requests.models.Response()
            response.status_code = 499
            response._content = str(e)
            response.url = url
        return response

    def send_as_chunked_payloads(self, scanner, metadata_types_to_send=None):

        send_order = [
            'datatype',
            'valuedomain',
            'distribution',
            'dataset',
        ]

        if not metadata_types_to_send:
            metadata_types_to_send = send_order
        else:
            metadata_types_to_send = [
                md_type for md_type in send_order
                if md_type in metadata_types_to_send
            ]

        metadata = scanner.metadata_as_priority_dict()

        total_items = scanner.metadata_count(metadata_type=metadata_types_to_send)
        items_sent = 0
        chunks_sent = 0

        for md_type in metadata_types_to_send:
            for priority, prioritised_items in metadata.get(md_type,{}).items():
                total_items_in_priority = len(prioritised_items)
                for chunk_number, items in self.create_metadata_for_payload(prioritised_items):
                    description = f"{md_type}.priority-{priority}.chunk-{chunk_number}.json"
                    json_data = {
                        "description": description,
                        "payload_data": {
                            md_type: items
                        },
                    }
                    items_in_chunk = len(items)
                    chunks_sent += 1
                    items_sent += items_in_chunk
                    response = self.send_payload(json_data)
                    yield {
                        'pipeline': self.pipeline,
                        'response': response,
                        'priority': priority,
                        'metadata_type': md_type,
                        'description': description,
                        'chunk_number': chunk_number,
                        'items_in_chunk': items_in_chunk,
                        'total_items_in_priority': total_items_in_priority,
                        'total_items_to_send': total_items,
                        'items_sent': items_sent,
                        'chunks_sent': chunks_sent,
                    }

    @property
    def chunk_item_size(self):
        return min(150, self.items_per_chunk)

    def create_metadata_for_payload(self, metadata_set):
        items = []

        items_in_chunk = 0
        chunk_items_size = 0
        chunks = 0
        for item in metadata_set:
            item_size = len(json.dumps(item).encode('utf-8'))
            payload_too_big = (
                (chunk_items_size + item_size > MAX_PAYLOAD_SIZE_IN_BYTES) or
                (items_in_chunk >= self.chunk_item_size)
            )
            if payload_too_big:
                # If the payload is too big, yield the result so it can be sent
                # Then we reset everything
                yield chunks, items
                items = []
                chunk_items_size = 0
                items_in_chunk = 0
                chunks += 1
            else:
                # If the payload is not too big, just continue
                # This else is just for clarity to show that either way
                # we need to append the current item to the current chunk or the new one.
                pass
                
            
            items.append(item)
            chunk_items_size += item_size
            items_in_chunk += 1

        yield chunks, items
