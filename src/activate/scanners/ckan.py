"""
CKAN scanner
===============

Scans a CKAN instance and finds all datasets, resources, etc and builds a dictionary from them.

"""

from activate.scanners.base import Scanner
from activate.utils.config import Config

import requests
from datetime import datetime
from turfpy.measurement import bbox
from geojson import Feature, FeatureCollection
import json

OMIT_FIELD = "Do not output this field in dictionary"

# We can't use truthiness, or None as both of these are valid values which we may want to retain and pass through.
VALUE_NOT_SET = "This value has not been set"

class CKANScanner(Scanner):
    name = "ckan"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ckan = self.config.config['connector']['options']
        self.ckan_search = self.prepare_search(self.ckan)
        self.ckan_url = self.config.config['connector']['options']['ckan_url'].rstrip('/')

    def prepare_search(self, ckan_config):
        search = ckan_config.get('search', {})
        return search

    @property
    def active_id_namespace(self):
        """
        Only return the safe parts of the database url for the namespace
        """
        return self.ckan_url

    def scan_datasets(self):
        self.progress.update(1, "Scanning CKAN datasets")

        url = self.ckan_url+"/api/3/action/package_search"
        response = requests.get(
            url,
            params=self.ckan_search
        )

        # R=response
        # from pdb import set_trace; set_trace()


        datasets = response.json().get('result', {}).get('results', [])
        
        for dataset in datasets:
            dataset = self.scan_dataset(dataset)
            self.add_metadata("dataset", dataset["uuid"], dataset)

        self.progress.finish()
        output = {
            item_type: list(item_dict.values())
            for item_type, item_dict in self._metadata.items()
        }

        return output

    def geojson_to_turfpy(self, geojson_obj):
        if type(geojson_obj) is str:
            try:
                geojson_obj = json.loads(geojson_obj)
            except:
                return None

        # Convert the dictionary to a Feature or FeatureCollection if needed
        if "type" in geojson_obj and geojson_obj["type"] == "FeatureCollection":
            return FeatureCollection(geojson_obj["features"])
        elif "type" in geojson_obj and geojson_obj["type"] == "Feature":
            return FeatureCollection([Feature(**geojson_obj)])
        else:
            return FeatureCollection([Feature(geometry=geojson_obj)])

    def field_to_aristotle(self, conf, source):
        """
        Maps and converts a single field to Aristotle's format.
        """
        final_value = VALUE_NOT_SET
        default_value = VALUE_NOT_SET
        if type(conf) is str:
            conf = {
                "type": "field",
                "field": conf
            }
            default_value = "Unknown value"

        if type(conf) is list:
            pass
        elif type(conf) is dict:
            if conf['type'] == 'concat':
                values = []
                for inner_conf in conf['values']:
                    values.append(self.field_to_aristotle(inner_conf, source))
                separator = conf.get('separator', '')
                final_value = separator.join(values)
            elif conf['type'] == 'field':
                final_value = source.get(conf['field'], None)
            elif conf['type'] == 'parse_date':
                value = source.get(conf['field'], None)
                if value:
                    try:
                        format_string = conf.get('format', '%Y-%m-%dT%H:%M:%S%z')
                        dt = datetime.strptime(value, format_string)
                        final_value = dt.isoformat()
                    except:
                        final_value = OMIT_FIELD
                else:
                    final_value = OMIT_FIELD
            elif conf['type'] == 'string':
                final_value = str(conf['value'])
            elif conf['type'] == 'literal':
                final_value = conf['value']
            elif conf['type'] == 'geojson_to_bbox':
                if geojson_obj := source.get(conf['field'], None):
                    tp = self.geojson_to_turfpy(geojson_obj)
                    bbox_coords = bbox(tp)
                    final_value = str(bbox_coords)
                else:
                    final_value = OMIT_FIELD
            elif conf['type'] == 'join':
                values = source.get(conf['field'], [])
                separator = conf.get('separator', '')
                if values:
                    final_value = separator.join(values)
            elif conf['type'] == 'list':
                values = []
                for inner_conf in conf['values']:
                    values.append(self.field_to_aristotle(inner_conf, source))
                final_value = values
            elif conf['type'] == 'dict':
                value = {}
                for key, item in conf['keys'].items():
                    output = self.field_to_aristotle(item, source)
                    if output != OMIT_FIELD:
                        value[key] = output
                final_value = value

            if default_value == VALUE_NOT_SET:
                default_value = conf.get("default", "Unknown value")
            if conf.get("on_null", "keep") == "set_default":
                final_value = VALUE_NOT_SET     

        if final_value == VALUE_NOT_SET:
            final_value = default_value
        return final_value


    def scan_dataset(self, source) -> dict:
        """
        Maps and converts a single dataset to Aristotle's format.
        """
        # Setup default dictionary
        dataset = {
            "uuid": self.make_active_id('dataset', source['id']),
            "name": source['title'],
            "datasetdistributionpath_set": [],
            "origin_URI": f"{self.ckan_url}/dataset/{source['id']}"
        }

        dataset_mapping = self.ckan.get('mapping', {}).get('dataset', {})
        for field, conf in dataset_mapping.items():
            output = self.field_to_aristotle(conf, source)
            if output != OMIT_FIELD:
                dataset[field] = output

        return dataset

    def scan_distribution(self, schema_name, table_name) -> dict:
        return {}
        """
        Scans an engine for a given table name and builds a data dictionary.
        """

        table = self.metadata.tables[table_name]
        dist = {
            "uuid": self.make_active_id('distribution', table.fullname),
            "name": str(table.name),
            # "updated_date": NOW
            "format_type": self.engine.name,    
            "distributiondataelementpath_set": [],
        }

        columns = table.columns
        for i, column in enumerate(columns):
            type_name = column.type.__class__.__name__
            active_datatype = {
                "name": type_name,
                "definition": f"An SQL primative datatype of type {type_name}",
            }
            active_datatype['uuid'] = self.make_constant_ns_id("datatype", active_datatype['name'])
            self.add_metadata("datatype", active_datatype["uuid"], active_datatype)

            active_value_domain = {
                "name": type_name,
                "definition": f"An SQL primative datatype of type {type_name}",
                "data_type": active_datatype['uuid']
            }
            if hasattr(column.type, 'length'):
                active_value_domain['name'] = f"{type_name}({column.type.length})"
                active_value_domain['maximum_length'] = column.type.length
            active_value_domain['uuid'] = self.make_constant_ns_id("valuedomain", active_value_domain['name'])
            self.add_metadata("valuedomain", active_value_domain["uuid"], active_value_domain)

            foreign_key = None
            if column.foreign_keys:
                # FKs are stored as a set - assume only one key.
                fkey = list(column.foreign_keys)[0]
                foreign_key = self.make_active_column_id(
                        fkey.column.table.fullname,
                        fkey.column.name
                    )

            path_id = self.make_active_column_id(table.name, column.name)
            col_data = {
                # Active content
                "activate": {
                    "id": path_id,
                    "active_datatype": active_datatype['uuid'],
                    "primary_key": column.primary_key,
                    "nullable": column.nullable,
                    "foreign_key": foreign_key,
                },
                "id": path_id,
                "order": i,
                "logical_path": str(column.name),
                #TODO: Change to accept VD or Glossary Item as well as data_element
                # "metadata": active_value_domain['uuid'],
            }

            dist["distributiondataelementpath_set"].append(col_data)

        return dist
