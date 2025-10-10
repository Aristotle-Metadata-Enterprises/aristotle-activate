import hashlib
from importlib import import_module
from collections import defaultdict
from sqlalchemy.ext.automap import automap_base
from activate.utils.exceptions import ActivateConfigError
from activate.utils.loaddb import prepare_engine
from activate.utils.progress import NullProgressReporter


scanners_register = {
}

def register(scanner_class):
    scanners_register[scanner_class.name] = scanner_class


# We can't use truthiness, or None as both of these are valid values which we may want to retain and pass through.
VALUE_NOT_SET = "This value has not been set"
OMIT_FIELD = "This field should be omitted"


class Scanner:
    namespace_separator = "::"
    hashing_method = hashlib.sha256

    def __init__(self, config, progress_callback=NullProgressReporter()):
        self.config = config
        self.progress = progress_callback
        self._metadata = defaultdict(dict)
        self._metadata_order = defaultdict(dict)

        self.activate_options = self.config.config.get('activate_options', {})
        ns_sep = self.activate_options.get('namespace_separator', None)
        if ns_sep is not None:
            # Check against none, as empty string is a valid entry
            self.namespace_separator = ns_sep

        if hash_method := self.activate_options.get('hashing_method', None):
            if hash_method == 'md5':
                self.hashing_method = hashlib.md5
            if hash_method == 'plaintext':
                self.hashing_method = lambda plaintext: plaintext
        self.output_plaintext_with_hash = bool(self.activate_options.get('output_plaintext_with_hash', False))

    def scan_datasets(self):
        raise NotImplementedError

    def scan_distributions(self):
        raise NotImplementedError

    @property
    def active_id_namespace(self: str) -> str:
        raise NotImplementedError

    def make_constant_ns_id(self, metadatatype: str, identifier: str) -> str:
        message = self.hashing_method(
            f"ARISTOTLE_ACTIVATE_NAMESPACE::{metadatatype}::{identifier}".encode("utf-8")
        ).hexdigest()
        return f"active_id:v1:{metadatatype}:{message}"

    def make_active_id(self, metadatatype, identifier: str) -> str:
        plaintext_id = f"{self.active_id_namespace}{self.namespace_separator}{identifier}"
        message = self.hashing_method(plaintext_id.encode("utf-8")).hexdigest()
        active_id = f"active_id:v1:{metadatatype}:{message}"
        if self.output_plaintext_with_hash:
            active_id = f"{active_id}#{plaintext_id}"
        return active_id

    def make_active_column_id(self, identifier: str, column_name: str) -> str:
        message = self.hashing_method(
            f"{self.active_id_namespace}{self.namespace_separator}{identifier}:{column_name}".encode("utf-8")
        ).hexdigest()
        return f"active_id:v1:dist_path:{message}"

    def make_active_table_link_id(self, identifier: str) -> str:
        message = self.hashing_method(
            f"{self.active_id_namespace}{self.namespace_separator}{identifier}".encode("utf-8")
        ).hexdigest()
        return f"active_id:v1:dataset_distribution:{message}"

    @classmethod
    def from_config(cls, config, progress_callback=NullProgressReporter()):
        con_type = config.config["connector"]["type"]

        try:
            module_name = ".".join(con_type.split(".")[:-1])
            scanner_class = con_type.split(".")[-1]
            import_module(module_name)

            Scanner = getattr(import_module(module_name), scanner_class)
            return Scanner(config, progress_callback)
        except:
            raise
            raise ActivateConfigError(f"Connection type '{con_type}' not supported")

        if con_type == "database":
            return AlchemyScanner(config, progress_callback)

        raise ActivateConfigError(f"Connection type '{con_type}' not supported")

    def add_metadata(self, item_type, active_id, item):
        # metadata = {
        #     "dataset": {},
        #     "distribution": {},
        #     "value_domain": {},
        #     "glossary_item": {},
        #     "data_element": {},
        # }
        self.setdefault_metadata_order(item_type, active_id, 0)
        self._metadata[item_type][active_id] = item

    def metadata_count(self, metadata_type=None):
        if metadata_type is None:
            return sum([len(v) for v in self._metadata.values()])
        elif type(metadata_type) is str:
            return len(self._metadata[metadata_type])
        else:
            return sum([
                len(v) for k,v in self._metadata.items()
                if k in metadata_type
            ])

    def setdefault_metadata_order(self, item_type, active_id, order_hint=0):
        if active_id not in self._metadata_order[item_type].keys():
            self._metadata_order[item_type][active_id] = order_hint

    def upsert_metadata_order(self, item_type, active_id, order_hint):
        self._metadata_order[item_type][active_id] = order_hint

    def upsert_metadata(self, item_type, active_id, item={}, order_hint=None):
        if item.get('uuid', None) is None:
            if active_id is not None:
                item['uuid'] = active_id
            else:
                return
        
        if order_hint is not None:
            self.upsert_metadata_order(item_type, active_id, order_hint)

        if active_id not in self._metadata[item_type].keys():
            self.add_metadata(item_type, active_id, item)
        
    def append_metadata_component(self, item_type, active_id, component_name, component, with_order=False):
        self.upsert_metadata(item_type, active_id)

        item = self._metadata[item_type][active_id]

        if component_name == "datasetdistributiongroup_set.datasetdistributionpath_set":
            if item.get('datasetdistributiongroup_set', None) is None:
                item['datasetdistributiongroup_set'] = {
                "name": "Root",
                "order": 0,
                "datasetdistributionpath_set": [],
            }
            components = item['datasetdistributiongroup_set']['datasetdistributionpath_set']
        elif component_name == "datasetdistributiongroup_set.datasetdatasetpath_set":
            if item.get('datasetdistributiongroup_set', None) is None:
                item['datasetdistributiongroup_set'] = {
                "name": "Root",
                "order": 0,
                "datasetdistributionpath_set": [],
                "datasetdatasetpath_set": [],
            }
            components = item['datasetdistributiongroup_set']['datasetdatasetpath_set']
        else:
            self._metadata[item_type][active_id].setdefault(component_name, [])
            components = self._metadata[item_type][active_id][component_name]

        if with_order:
            component['order'] = len(components)

        components.append(component)


    def scan_metadata(self):
        self.scan_datasets()

    def metadata_as_dict(self):
        output = {}
        for item_type, item_dict in self._metadata.items():
            def order_hint(item):
                return self._metadata_order[item_type].get(item['uuid'], 0)

            output[item_type] = sorted(
                item_dict.values(),
                key=order_hint
            )  
        return output

    def metadata_as_priority_dict(self):
        output = {}
        for md_type, order_hints in self._metadata_order.items():
            output[md_type] = {}
            for item_id, hint in order_hints.items():
                output[md_type].setdefault(hint, [])
                output[md_type][hint].append(self._metadata[md_type][item_id])
            
        return output
        
    def field_to_aristotle_component(self, item, component_name, component):
        component = []

        if component_name == "datasetdistributiongroup_set":
            if item.get('datasetdistributiongroup_set', None) is None:
                item['datasetdistributiongroup_set'] = {
                "name": "Root",
                "order": 0,
                "datasetdistributionpath_set": [],
            }
            components = item['datasetdistributiongroup_set']['datasetdistributionpath_set']

        components.append(component)

    def field_to_aristotle(self, conf, source):
        """
        Maps and converts a single field to Aristotle's format.
        source is a dictionary of keys/values
        conf is an aristotle field configuration

        1. If conf is a string, it is the name of the field to extract
        2. If conf is a list, it is a list of field configurations to extract and concatenate
        3. If conf is a dict, it is a configuration for a specific operation
            a. type: concat - concatenate a list of field configurations
            b. type: field - extract a single field
            c. type: parse_date - extract a single field and parse it as a date
            d. type: string - return a constant from the configuration cast as a string
            e. type: literal - return a constant from the configuration without any data type modification
            f. type: geojson_to_bbox - extract a geojson field and convert it to a bbox
            g. type: join - extract a list field and join it with a separator
            h. type: list - extract a list of field configurations and return as a list
            i. type: dict - extract a dict of field configurations and return as a dict
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
            if 'type' not in conf.keys():
                raise ActivateConfigError(f"Field configuration must have a type: {conf}")

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
            elif conf['type'] == 'active_id':
                final_value = self.spec_to_active_id(conf['metadata_type'], conf['active_id'], source)
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

    def spec_to_active_id(self, metadatatype, conf, row):
        fields = [conf['prefix']]
        for column in conf['columns']:
            if field := row.get(column, None):
                fields.append(field.strip())
            else:
                return None
        identifier = '+'.join(fields)
        return self.make_active_id(metadatatype, identifier)

