"""
Activate scanner
===============

Scans an SQLAlchemy metadata object and finds all tables, views, etc and builds a dictionary from them.

"""

from activate.scanners.base import Scanner
from activate.utils.config import Config

from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session
from sqlalchemy import inspect, create_engine, MetaData


def prepare_engine(config: Config):
    Base = automap_base()

    # engine, suppose it has two tables 'user' and 'address' set up
    engine = create_engine(config.config["connector"]["options"]["database_url"])

    # reflect the tables
    Base.prepare(autoload_with=engine)
    # meta = MetaData(engine)
    # meta.reflect(bind=engine, views=True)
    meta = None
    # return Base
    return inspect(engine), meta


class AlchemyScanner(Scanner):
    name = "alchemy"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inspector, self.othermeta = prepare_engine(self.config)
        self.engine = self.inspector.engine

        Base = automap_base()
        for i, schema in enumerate(self.inspector.get_schema_names()):
            Base.prepare(autoload_with=self.engine, schema=schema)

        self.metadata = Base.metadata
        self.metadata.reflect(bind=self.engine, extend_existing=True, views=True)
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
            if self.is_system_schema(schema_name):
                continue
            dataset = self.scan_dataset(schema_name)
            self.add_metadata("dataset", dataset["uuid"], dataset)

        self.calc_order_hints()

        self.progress.finish()

    def calc_order_hints(self):
        def _build_distribution_graph(_distributions:list):
            _graph = {}
            for _distribution in _distributions:
                _dependencies = set([
                    _src
                    for _item in _distribution.get("distributionprovenance_set", [])
                    for _src in _item.get("source_distributions", [])
                ])
                _graph[_distribution["uuid"]] = _dependencies
            return _graph

        from toposort import toposort
        order_hint = 1
        for item_type in ("datatype", "valuedomain"):
            for active_id in self._metadata.get(item_type, {}).keys():
                self.upsert_metadata_order(item_type, active_id, order_hint)
            order_hint += 1

        distribution_graph = _build_distribution_graph(list(self._metadata.get("distribution", {}).values()))
        print(distribution_graph)
        for level in toposort(distribution_graph):
            for item in level:
                self.upsert_metadata_order("distribution", item, order_hint)
            order_hint += 1

        for active_id in self._metadata.get("dataset", {}).keys():
            self.upsert_metadata_order("dataset", active_id, order_hint)

    def is_system_schema(self, schema_name):
        engine_name = self.engine.name.lower()
        schema_name = schema_name.lower()
        if engine_name == "mysql":
            return schema_name in ("information_schema", "mysql", "performance_schema", "sys")
        elif engine_name == "postgresql":
            return schema_name.startswith("pg_") or schema_name == "information_schema"
        elif engine_name == "mssql":
            return schema_name.startswith("sys") or schema_name == "information_schema" or schema_name == "guest" or schema_name.startswith("db_")
        elif engine_name == "sqlite":
            return False
        return False

    def extract_tables_from_view(self, view_name: str):
        """
        Given a view definition SQL, extract the source tables used in the view.
        """
        from sqlglot import parse_one, exp
        import re

        view_def = self.inspector.get_view_definition(view_name)

        try:
            match = re.search(r'\bAS\b\s+(SELECT\b.*)', view_def, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                return []

            select_sql = match.group(1).strip().rstrip(';')

            dialect = self.engine.dialect.name
            if dialect == "mssql":
                dialect = "tsql"
            ast = parse_one(select_sql, dialect=dialect)
            tables = [t.name for t in ast.find_all(exp.Table)]
            return list(set(tables))
        except Exception as e:
            self.logger.error(f'Unable to get source tables for view: {view_name}, error: {e}')
            return []


    def scan_dataset(self, schema_name) -> dict:
        """
        Scans a schema engine and finds all tables, views, etc and builds a dictionary from them.
        """

        dataset = {
            "uuid": self.make_active_id('dataset', schema_name),
            "name": schema_name,
            "datasetdistributionpath_set": [],
            "datasetdistributiongroup_set": {
                "name": "Root",
                "order": 0,
            }
        }

        table_names = self.inspector.get_table_names(schema=schema_name)
        view_names = self.inspector.get_view_names(schema=schema_name)
        datasetdistributionpath_set = []
        for i, table in enumerate(table_names + view_names):
            source_table_names = []
            if table in view_names:
                source_table_names = self.extract_tables_from_view(table)

            distribution = self.scan_distribution(schema_name, table, source_table_names)

            self.add_metadata("distribution", distribution["uuid"], distribution)

            dataset_dist_id = self.make_active_table_link_id(table)
            datasetdistributionpath_set.append(
                {
                    "order": i,
                    "distribution": distribution["uuid"],
                }
            )
            self.progress.add(100 / self.number_of_tables)
        if datasetdistributionpath_set:
            dataset["datasetdistributiongroup_set"]["datasetdistributionpath_set"] = datasetdistributionpath_set
        return dataset

    def scan_distribution(self, schema_name, table_name, source_table_names=[]) -> dict:
        """
        Scans an engine for a given table name and builds a data dictionary.
        """

        table = self.metadata.tables[table_name]
        dist = {
            "uuid": self.make_active_id('distribution', table.fullname),
            "name": str(table.name),
            # "updated_date": NOW
            "format_type": self.engine.name,    
            "distributiondataelementpath_set": []
        }

        if source_table_names:
            # I'm not sure here - we need to create the active IDs for the source tables
            for i, view_table in enumerate(source_table_names):
                dist.setdefault('distributionprovenance_set', []).append({
                    "source_distributions": [
                        self.make_active_id('distribution', view_table),
                    ],
                    "generation": "",
                    "release_date": None,
                    "order": i
                })

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
                print('fkey', fkey.column.table.fullname, fkey.column.name)

            path_id = self.make_active_column_id(table.name, column.name)
            col_data = {
                # Active content
                "activate": {
                    "id": path_id,
                    "active_datatype": active_datatype['uuid'],
                    "primary_key": column.primary_key,
                    "nullable": column.nullable,
                    "foreign_key": None, # todo, remove foreign_key for test
                },
                "id": path_id,
                "order": i,
                "logical_path": str(column.name),
                #TODO: Change to accept VD or Glossary Item as well as data_element
                # "metadata": active_value_domain['uuid'],
            }

            dist["distributiondataelementpath_set"].append(col_data)

        return dist
