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
from lxml import etree

OMIT_FIELD = "Do not output this field in dictionary"
NAMESPACES = {
    'message': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message',
    'structure': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure',
    'common': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common'
}


class DotStatScanner(Scanner):
    name = "ckan"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dotstat = self.config.config['connector']['options']
        self.dotstat_api_url = self.config.config['connector']['options']['dotstat_api_url'].rstrip('/')
        self.dotstat_url = self.config.config['connector']['options']['dotstat_url'].rstrip('/')

    @property
    def active_id_namespace(self):
        """
        Only return the safe parts of the database url for the namespace
        """
        return self.dotstat_api_url

    def multilingual_text(self, element_name, xml):
        elems = xml.findall(element_name, namespaces=NAMESPACES)
        if elems is not None:
            return {
                k.attrib['{http://www.w3.org/XML/1998/namespace}lang']: k.text
                for k in elems
            }
        return {"en": "No name found"}

    def first_multilingual_text(self, element_name, xml):
        elem = xml.find(element_name, namespaces=NAMESPACES)
        if elem is not None:
            return elem.text
        return "No name found"

    def scan_datasets(self):
        self.progress.update(1, "Scanning Dotstat datasets")

        url = self.dotstat_api_url+"/rest/dataflow/all"
        response = requests.get(
            url,
            params={}
        )

        tree = etree.fromstring(response.text.encode('utf-8'))

        dataflows = tree.findall('./message:Structures/structure:Dataflows/structure:Dataflow', namespaces=NAMESPACES)

        for df in dataflows[:1]:
            df_id = df.attrib.get('id', None)
            df_agency_id = df.attrib.get('agencyID', None)
            dataset = {
                "uuid": self.make_active_id('dataset', df_id),
                # "name": self.multilingual_text('./common:Name', df),
                # "description": self.multilingual_text('common:Description', df),
                "name": self.first_multilingual_text('./common:Name', df),
                "description": self.first_multilingual_text('common:Description', df),
                "origin_uri": f"{self.dotstat_url}/vis?vw=ov&df[ds]=ds%3A{df_agency_id}2&df[id]={df_id}&df[ag]={df_agency_id}"
            }
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
        if type(conf) is list:
            pass
        elif type(conf) is str or conf['type'] == 'field':
            if type(conf) is str:
                value = source.get(conf, None)
            else:
               value = source.get(conf['field'], None) 
            if value:
                return value
            else:
                return 'Unknown value'
        elif conf['type'] == 'parse_date':
            value = source.get(conf['field'], None)
            if value:
                try:
                    format_string = conf.get('format', '%Y-%m-%dT%H:%M:%S%z')
                    dt = datetime.strptime(value, format_string)
                    return dt.isoformat()
                except:
                    return OMIT_FIELD
            else:
                return OMIT_FIELD
        elif conf['type'] == 'string':
            return conf['value']
        elif conf['type'] == 'geojson_to_bbox':
            if geojson_obj := source.get(conf['field'], None):
                tp = self.geojson_to_turfpy(geojson_obj)
                bbox_coords = bbox(tp)
                return bbox_coords
            else:
                return OMIT_FIELD
        elif type(conf) is dict:
            if conf['type'] == 'concat':
                values = []
                for inner_conf in conf['values']:
                    values.append(self.field_to_aristotle(inner_conf, source))
                separator = conf.get('separator', '')
                return separator.join(values)
            if conf['type'] == 'join':
                values = source.get(conf['field'], [])
                separator = conf.get('separator', '')
                return separator.join(values)
            if conf['type'] == 'dict':
                value = {}
                for key, item in conf['keys'].items():
                    output = self.field_to_aristotle(item, source)
                    if output != OMIT_FIELD:
                        value[key] = output
                return value
        return ""


    def scan_dataset(self, source) -> dict:
        """
        Maps and converts a single dataset to Aristotle's format.
        """
        # Setup default dictionary
        dataset = {
            "uuid": self.make_active_id('dataset', source['id']),
            "name": source['title'],
            "datasetdistributionpath_set": [],
            "origin_uri": f"{self.dotstat_api_url}/dataset/{source['id']}"
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
