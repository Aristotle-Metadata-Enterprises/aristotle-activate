"""
Metamapper CSV scanner
======================

Scans a CSV File and tries to process it into Aristotle things

"""

import csv

from activate.scanners.base import Scanner


class MetaMapperScanner(Scanner):
    name = "metamapper"

    def __init__(self, *args, file_path=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = self.config.config['connector']['options']
        # Caller-supplied file_path takes priority over the YAML 'file' key.
        # The YAML 'file' key remains supported so existing CLI invocations
        self._file_path = file_path
        self._active_ids_with_uuids = {}

    @property
    def file_path(self):
        """Resolve the CSV path: caller-supplied wins, else YAML 'file' key."""
        if self._file_path:
            return self._file_path
        return self.options.get('file')

    @property
    def active_id_namespace(self):
        """
        Only return the safe parts of the database url for the namespace
        """
        return self.options.get('prefix', "")

    def scan_metadata(self):
        return self.scan_rows()

    def scan_rows(self):
        path = self.file_path
        if not path:
            from activate.utils.exceptions import ActivateConfigError
            raise ActivateConfigError(
                "No CSV file provided: pass file_path to MetaMapperScanner "
                "or set 'file' under connector.options in the YAML."
            )
        with open(path) as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if not any(value and value.strip() for value in row.values()):
                    continue
                self.row_to_metadata(row)

    def row_to_metadata(self, row):
        self._active_ids_with_uuids = {}

        for md_conf in self.options.get('metadata_types', []):
            md_type = md_conf['metadata_type']
            active_id = self.spec_to_active_id(md_type, md_conf['active_id'], row)
            item = self.conf_to_item(md_conf, row)

    def conf_to_item(self, conf, row):
        md_type = conf['metadata_type']
        active_id = self.spec_to_active_id(md_type, conf['active_id'], row)

        item = {}
        for field, value in conf.get('fields', {}).items():
            item[field] = self.field_to_aristotle(value, row)

        if on_create := conf.get('on_create', {}):
            item['on_create'] = {}
            for field, value in on_create.items():
                item['on_create'][field] = self.field_to_aristotle(value, row)

        active_id = self.normalise_uuid(item, md_type, active_id)
        self.upsert_metadata(md_type, active_id, item, order_hint=conf.get('order_hint', None))

        for field, comp_conf in conf.get('components', {}).items():
            component = {}
            for sub_field, value in comp_conf.get('fields', {}).items():
                resolved = self.field_to_aristotle(value, row)
                component[sub_field] = self.normalise_active_id_reference(resolved)

            with_order = bool(comp_conf.get('with_order', False))

            self.append_metadata_component(md_type, active_id, field, component, with_order)

        return item

    def normalise_uuid(self, item, md_type, active_id):
        has_uuid_field = 'uuid' in item
        supplied_uuid = (item.get('uuid') or '').strip()

        if not supplied_uuid:
            item.pop('uuid', None)

            if has_uuid_field and (
                    active_id is None or active_id in self._metadata[md_type]
            ):
                active_id = self.make_active_id(
                    md_type,
                    f'{active_id}:{len(self._metadata[md_type])}',
                )

            return active_id

        if active_id is None:
            active_id = self.make_active_id(md_type, supplied_uuid)

        item['uuid'] = f'{active_id}:{supplied_uuid}'
        self._active_ids_with_uuids[active_id] = item['uuid']
        return active_id

    def normalise_active_id_reference(self, value):
        if isinstance(value, dict):
            return {
                key: self.normalise_active_id_reference(item)
                for key, item in value.items()
            }

        if isinstance(value, list):
            return [
                self.normalise_active_id_reference(item)
                for item in value
            ]

        if isinstance(value, str):
            return self._active_ids_with_uuids.get(value, value)

        return value