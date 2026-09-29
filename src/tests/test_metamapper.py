# PYTHONPATH=src uv run python -m unittest tests.test_metamapper -v
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from activate.scanners.metamapper import MetaMapperScanner


class MetaMapperScannerTests(unittest.TestCase):
    def make_scanner(self, file_path=None):
        options = {
            'prefix': 'test',
        }

        if file_path:
            options['file'] = file_path

        config = SimpleNamespace(config={
            'connector': {
                'options': options,
            },
        })

        return MetaMapperScanner(config)

    def test_blank_row_is_skipped(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv') as csv_file:
            csv_file.write('uuid,name\n,\n')
            csv_file.flush()

            scanner = self.make_scanner(csv_file.name)

            with patch.object(scanner, 'row_to_metadata') as row_to_metadata:
                scanner.scan_rows()

            row_to_metadata.assert_not_called()

    def test_supplied_uuid_is_appended_to_active_id(self):
        scanner = self.make_scanner()
        supplied_uuid = '9bb5adbe-94b1-4f30-8895-5916ffbbb21d'
        conf = {
            'metadata_type': 'dataset',
            'active_id': {
                'prefix': 'Dataset',
                'columns': ['name'],
            },
            'fields': {
                'uuid': 'uuid',
                'name': 'name',
            },
        }
        row = {
            'uuid': supplied_uuid,
            'name': 'Updated dataset',
        }

        item = scanner.conf_to_item(conf, row)
        active_id = scanner.make_active_id('dataset', 'Dataset+Updated dataset')

        self.assertEqual(item['uuid'], f'{active_id}:{supplied_uuid}')

    def test_uuid_is_used_for_active_id_when_name_is_blank(self):
        scanner = self.make_scanner()
        supplied_uuid = '9bb5adbe-94b1-4f30-8895-5916ffbbb21d'
        conf = {
            'metadata_type': 'dataset',
            'active_id': {
                'prefix': 'Dataset',
                'columns': ['name'],
            },
            'fields': {
                'uuid': 'uuid',
                'name': 'name',
            },
        }
        row = {
            'uuid': supplied_uuid,
            'name': '',
        }

        item = scanner.conf_to_item(conf, row)
        active_id = scanner.make_active_id('dataset', supplied_uuid)

        self.assertEqual(item['uuid'], f'{active_id}:{supplied_uuid}')
        self.assertEqual(item['name'], '')

    def test_blank_uuid_is_removed(self):
        scanner = self.make_scanner()
        item = {
            'uuid': '',
            'name': 'New dataset',
        }
        active_id = scanner.make_active_id('dataset', 'Dataset+New dataset')

        returned_active_id = scanner.normalise_uuid(
            item,
            'dataset',
            active_id,
        )

        self.assertEqual(returned_active_id, active_id)
        self.assertNotIn('uuid', item)

    def test_blank_uuid_with_same_name_is_not_merged(self):
        scanner = self.make_scanner()
        conf = {
            'metadata_type': 'dataset',
            'active_id': {
                'prefix': 'Dataset',
                'columns': ['name'],
            },
            'fields': {
                'uuid': 'uuid',
                'name': 'name',
            },
        }

        scanner.conf_to_item(conf, {
            'uuid': '9bb5adbe-94b1-4f30-8895-5916ffbbb21d',
            'name': 'Same dataset name',
        })
        scanner.conf_to_item(conf, {
            'uuid': '',
            'name': 'Same dataset name',
        })

        items = scanner.metadata_as_dict()['dataset']

        self.assertEqual(len(items), 2)

    def test_component_active_id_uses_supplied_uuid(self):
        scanner = self.make_scanner()
        supplied_uuid = 'f5e98096-bba0-11f1-85ae-3ad39c79e97f'
        distribution_active_id = scanner.make_active_id(
            'distribution',
            'Distribution+Updated distribution',
        )

        item = {
            'uuid': supplied_uuid,
            'name': 'Updated distribution',
        }

        scanner.normalise_uuid(
            item,
            'distribution',
            distribution_active_id,
        )

        reference = scanner.normalise_active_id_reference(
            distribution_active_id
        )

        self.assertEqual(
            reference,
            f'{distribution_active_id}:{supplied_uuid}',
        )

if __name__ == '__main__':
    unittest.main()
