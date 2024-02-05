import hashlib
from importlib import import_module
from collections import defaultdict
from sqlalchemy.ext.automap import automap_base
from activate.utils.exceptions import ConfigError
from activate.utils.loaddb import prepare_engine
from activate.utils.progress import NullProgressReporter

scanners_register = {
}

def register(scanner_class):
    scanners_register[scanner_class.name] = scanner_class


class Scanner:
    def __init__(self, config, progress_callback=NullProgressReporter()):
        self.config = config
        self.progress = progress_callback
        self._metadata = defaultdict(dict)

    def scan_datasets(self):
        raise NotImplementedError

    def scan_distributions(self):
        raise NotImplementedError

    @property
    def active_id_namespace(self: str) -> str:
        raise NotImplementedError

    def make_constant_ns_id(self, metadatatype: str, identifier: str) -> str:
        message = hashlib.sha256(
            f"ARISTOTLE_ACTIVATE_NAMESPACE::{metadatatype}::{identifier}".encode("utf-8")
        ).hexdigest()
        return f"active_id:v1:{metadatatype}:{message}"

    def make_active_id(self, metadatatype, identifier: str) -> str:
        message = hashlib.sha256(
            f"{self.active_id_namespace}::{identifier}".encode("utf-8")
        ).hexdigest()
        return f"active_id:v1:{metadatatype}:{message}"

    def make_active_column_id(self, identifier: str, column_name: str) -> str:
        message = hashlib.sha256(
            f"{self.active_id_namespace}::{identifier}:{column_name}".encode("utf-8")
        ).hexdigest()
        return f"active_id:v1:dist_path:{message}"

    def make_active_table_link_id(self, identifier: str) -> str:
        message = hashlib.sha256(
            f"{self.active_id_namespace}:{identifier}".encode("utf-8")
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
            raise ConfigError(f"Connection type '{con_type}' not supported")

        if con_type == "database":
            return AlchemyScanner(config, progress_callback)

        raise ConfigError(f"Connection type '{con_type}' not supported")

    def add_metadata(self, item_type, active_id, item):
        # metadata = {
        #     "dataset": {},
        #     "distribution": {},
        #     "value_domain": {},
        #     "glossary_item": {},
        #     "data_element": {},
        # }
        self._metadata[item_type][active_id] = item
