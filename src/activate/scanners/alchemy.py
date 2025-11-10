"""
Activate scanner
===============

Scans an SQLAlchemy metadata object and finds all tables, views, etc and builds a dictionary from them.

"""
import re

from activate.scanners.base import Scanner
from activate.utils.config import Config

from sqlalchemy.ext.automap import automap_base
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
        self.views = {}
        self.tables = {}

        for i, schema in enumerate(self.inspector.get_schema_names()):
            if self.is_system_schema(schema.lower()):
                continue
            Base.prepare(autoload_with=self.engine, schema=schema)

        self.find_tables()
        self.find_views()

        self.metadata = Base.metadata
        self.number_of_tables = len(self.metadata.tables)
        self.number_of_views = len(self.views)
        print('number_of_views', self.number_of_views)

    @property
    def active_id_namespace(self):
        """
        Only return the safe parts of the database url for the namespace
        """
        url = self.engine.url
        namespace = f"{url.drivername}://{url.host}:{url.port}/{url.database}"
        return namespace

    def find_tables(self):
        for i, schema in enumerate(self.inspector.get_schema_names()):
            if self.is_system_schema(schema.lower()):
                continue
            tables = []
            for table_name in self.inspector.get_table_names(schema=schema):
                columns = self.inspector.get_columns(table_name=table_name, schema=schema)
                table_columns = []
                for column in columns:
                    table_columns.append(column)
                tables.append({
                    'name':table_name,
                    'columns': table_columns
                })

            self.tables[schema] = tables

    def find_views(self):
        view_def_pattern = r'(?:FROM|JOIN)\s+\(?[`"]?([\w\.]+)[`"]?(?:\s+[`\w]+)?'
        for i, schema in enumerate(self.inspector.get_schema_names()):
            if self.is_system_schema(schema.lower()):
                continue
            views = []
            for view_name in self.inspector.get_view_names(schema=schema):
                columns = self.inspector.get_columns(table_name=view_name, schema=schema)
                view_columns = []
                for column in columns:
                    view_columns.append(column)

                view_def = self.inspector.get_view_definition(view_name=view_name, schema=schema)
                view_tables = re.findall(view_def_pattern, view_def, flags=re.IGNORECASE)
                view_tables = [f'{schema}.{x}' for x in view_tables]
                views.append({
                    'name': view_name,
                    'columns': view_columns,
                    'view_tables': view_tables,
                })

            self.views[schema] = views

    def is_system_schema(self, schema_name):
        engine_name = self.engine.name.lower()
        if engine_name == "mysql":
            return schema_name.lower() in ("information_schema", "mysql", "performance_schema", "sys")
        elif engine_name == "postgresql":
            return schema_name.lower().startswith("pg_") or schema_name.lower() == "information_schema"
        elif engine_name == "sqlite":
            return False
        return False

    def scan_datasets(self):
        self.progress.update(1, "Scanning database tables")

        all_items = self.tables.copy()
        for schema in all_items.keys():
            all_items[schema].extend(self.views.get(schema, []))

        for schema_name, tables in all_items.items():
            dataset = self.scan_dataset(schema_name, tables)
            self.add_metadata('dataset', dataset["uuid"], dataset)
        self.progress.finish()

    def scan_dataset(self, schema_name, tables:list) -> dict:
        """
        Scans a schema engine and finds all tables, views, etc and builds a dictionary from them.
        """

        dataset = {
            "uuid": self.make_active_id('dataset', schema_name),
            "name": schema_name,
            "datasetdistributionpath_set": [],
        }

        for i, table in enumerate(tables):
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

    def scan_distribution(self, schema_name, table) -> dict:
        """
        Scans an engine for a given table name and builds a data dictionary.
        """
        fullname = f"{schema_name}.{table['name']}"
        dist = {
            "uuid": self.make_active_id('distribution', fullname),
            "name": str(table['name']),
            # "updated_date": NOW
            "format_type": self.engine.name,
            "distributiondataelementpath_set": [],
        }
        view_tables = table.get('view_tables', [])
        for i, view_table in enumerate(view_tables):
            dist.setdefault('distributionprovenance_set', []).append({
                    "source_distributions": [
                        self.make_active_id('distribution', view_table),
                    ],
                    "generation": "",
                    "release_date": None,
                    "order": i
                })

        columns = table['columns']
        for i, column in enumerate(columns):
            type_name = column['type'].__class__.__name__
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
            if hasattr(column['type'], 'length'):
                active_value_domain['name'] = f"{type_name}({column['type'].length})"
                active_value_domain['maximum_length'] = column['type'].length
            active_value_domain['uuid'] = self.make_constant_ns_id("valuedomain", active_value_domain['name'])
            self.add_metadata("valuedomain", active_value_domain["uuid"], active_value_domain)

            foreign_key = getattr(column, 'foreign_keys', None)
            if foreign_key:
                # FKs are stored as a set - assume only one key.
                fkey = list(column.foreign_keys)[0]
                foreign_key = self.make_active_column_id(
                    fkey.column.table.fullname,
                    fkey.column.name
                )

            path_id = self.make_active_column_id(table['name'], column['name'])
            col_data = {
                # Active content
                "activate": {
                    "id": path_id,
                    "active_datatype": active_datatype['uuid'],
                    "primary_key": getattr(column, 'primary_key', None),
                    "nullable": column['nullable'],
                    "foreign_key": foreign_key,
                },
                "id": path_id,
                "order": i,
                "logical_path": str(column['name']),
                # TODO: Change to accept VD or Glossary Item as well as data_element
                # "metadata": active_value_domain['uuid'],
            }

            dist["distributiondataelementpath_set"].append(col_data)

        return dist
