"""
Activate scanner
===============

Scans an SQLAlchemy metadata object and finds all tables, views, etc and builds a dictionary from them.

"""

from activate.scanners.base import Scanner
from activate.utils.config import Config

from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session
from sqlalchemy import inspect, create_engine


def prepare_engine(config: Config):
    Base = automap_base()

    # engine, suppose it has two tables 'user' and 'address' set up
    engine = create_engine(config.config["connector"]["options"]["database_url"])

    # reflect the tables
    Base.prepare(autoload_with=engine)
    # return Base
    return inspect(engine)


class AlchemyScanner(Scanner):
    name = "alchemy"

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
        Only return the safe parts of the database url for the namespace
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

    def scan_dataset(self, schema_name) -> dict:
        """
        Scans a schema engine and finds all tables, views, etc and builds a dictionary from them.
        """

        dataset = {
            "uuid": self.make_active_id('dataset', schema_name),
            "name": schema_name,
            "datasetdistributionpath_set": [],
        }

        for i, table in enumerate(self.metadata.tables.keys()):
            if table.startswith(f"{schema_name}."):
                distribution = self.scan_distribution(schema_name, table)
                self.add_metadata("distribution", distribution["uuid"], distribution)

                dataset_dist_id = self.make_active_table_link_id(table)
                dataset["datasetdistributionpath_set"].append(
                    {
                        "activate": {
                            "id": dataset_dist_id,
                        },
                        "id": dataset_dist_id,
                        "order": i,
                        "distribution": distribution["uuid"],
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
                # "data_type": active_datatype['uuid']
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
