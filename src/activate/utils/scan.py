"""
Activate scanner
===============

Scans an SQLAlchemy metadata object and finds all tables, views, etc and builds a dictionary from them.

"""
import hashlib
from collections import defaultdict
from sqlalchemy.ext.automap import automap_base
from activate.utils.exceptions import ConfigError
from activate.utils.loaddb import prepare_engine
from activate.utils.progress import NullProgressReporter


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
        # message = f"{self.active_id_namespace}::{identifier}"
        return f"activate_id:v1:{message}"

    def make_active_id(self, identifier: str) -> str:
        message = hashlib.sha256(
            f"{self.active_id_namespace}::{identifier}".encode("utf-8")
        ).hexdigest()
        # message = f"{self.active_id_namespace}::{identifier}"
        return f"activate_id:v1:{message}"

    def make_active_column_id(self, identifier: str, column_name: str) -> str:
        message = hashlib.sha256(
            f"{self.active_id_namespace}::{identifier}".encode("utf-8")
        ).hexdigest()
        # message = f"{self.active_id_namespace}::{identifier}"
        return f"activate_column_id:v1:{message}:{column_name}"

    @classmethod
    def from_config(cls, config, progress_callback=NullProgressReporter()):
        con_type = config.config["connector"]["type"]

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


class AlchemyScanner(Scanner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inspector = prepare_engine(self.config)
        self.engine = self.inspector.engine

        Base = automap_base()
        for i, schema in enumerate(self.inspector.get_schema_names()):
            Base.prepare(autoload_with=self.engine, schema=schema)

        self.metadata = Base.metadata
        self.number_of_tables = len(self.metadata.tables)

    @property
    def active_id_namespace(self):
        """
        Only return the safe parts of the databse url for the namespace
        """
        url = self.engine.url
        namespace = f"{url.drivername}://{url.host}:{url.port}/{url.database}"
        return namespace

    def get_dataset_names(self):
        return self.inspector.get_schema_names()

    def scan_datasets(self):
        self.progress.update(1, "Scanning database tables")
        dataset_names = self.get_dataset_names()
        for schema_name in dataset_names:
            dataset = self.scan_dataset(schema_name)
            self.add_metadata("dataset", dataset["uuid"], dataset)

        self.progress.finish()
        output = {
            item_type: list(item_dict.values())
            for item_type, item_dict in self._metadata.items()
        }

        return output

    def scan_dataset(self, schema_name) -> dict:
        """
        Scans a schema engine and finds all tables, views, etc and builds a dictionary from them.
        """

        dataset = {
            "uuid": self.make_active_id(schema_name),
            "name": schema_name,
            "datasetdistributionpath_set": [],
        }

        for i, table in enumerate(self.metadata.tables.keys()):
            if table.startswith(f"{schema_name}."):
                distribution = self.scan_distribution(schema_name, table)
                self.add_metadata("distribution", distribution["uuid"], distribution)

                dataset["datasetdistributionpath_set"].append(
                    {
                        "order": i,
                        "uuid": distribution["uuid"],
                    }
                )
                self.progress.add(100 / self.number_of_tables)

        return dataset

    def scan_distribution(self, schema_name, table_name) -> dict:
        """
        Scans an engine for a given table name and builds a data dictionary.
        """

        table = self.metadata.tables[table_name]
        dist = {
            "uuid": self.make_active_id(table.fullname),
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
                "datatype": active_datatype['uuid']
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

            col_data = {
                "order": i,
                "logical_path": str(column.name),

                #TODO: Change to accept VD or Glossary Item as well as data_element
                "metadata": active_value_domain['uuid'],

                # Active content
                "primary_key": column.primary_key,
                "active_datatype": active_datatype['uuid'],
                "nullable": column.nullable,
                "foreign_key": foreign_key,
            }

            dist["distributiondataelementpath_set"].append(col_data)

        return dist
