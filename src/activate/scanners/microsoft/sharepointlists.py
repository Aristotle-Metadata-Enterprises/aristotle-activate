"""
"""
from dataclasses import dataclass

from activate.scanners.base import Scanner, VALUE_NOT_SET
from activate.utils.config import Config

from datetime import datetime
from activate.scanners.microsoft.graph import Graph



class SharepointListScanner(Scanner):
    """
    Permissions required in Azure:
    Site.ReadAll
    Lists.SelectedOperations.Selected

    """


    name = "metamapper"
    required_secret_args = [
        'clientSecret',
    ]
    conn = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = self.config.config['connector']['options']

    @property
    def connector(self):
        if self.conn is None:
            self.graph: Graph = Graph({
                'clientId': self.options['clientId'],
                'clientSecret': self.secret_args['clientSecret'],
                'tenantId': self.options['tenantId']
            })
            self.conn = Connector(self.graph, self.options.get('siteId'))

        return self.conn

    @property
    def active_id_namespace(self):
        """
        Only return the safe parts of the database url for the namespace
        """
        return self.options.get('prefix', "")

    async def scan_metadata(self):
        print(self.secret_args)

        lists = await self.connector.get_sharepoint_lists()
        
        for slist in lists:
            print(slist.name, slist.web_url)
            print(slist)
            distribution = await self.list_to_distribution(slist)
            self.add_metadata("distribution", distribution["uuid"], distribution)

        return self

    async def list_to_distribution(self, slist):
        distribution = {
            # Assume that URL is unique
            "uuid": self.make_active_id('distribution', slist.web_url),
            "name": slist.name,
            "distributiondataelementpath_set": [],
            "origin_URI": slist.web_url,
        }
        
        distribution['distributiondataelementpath_set'] = await self.columns_to_paths(slist)

        return distribution

    async def columns_to_paths(self, slist):
        # https://learn.microsoft.com/en-us/graph/api/resources/columndefinition?view=graph-rest-1.0

        columns = await self.connector.get_list_columns(slist.id)
        print("Columns:", [col.name for col in columns])
        columns_data = []
        for i, column in enumerate(columns):

            path_id = self.make_active_column_id(slist.id, column.id)
            col_data = {
                # Active content
                "activate": {
                    "id": path_id,
                    "active_datatype": None,
                    "primary_key": False,
                    "nullable": False,
                    "foreign_key": False,
                },
                "id": path_id,
                "order": i,
                "logical_path": str(column.display_name),
                "specific_information": str(column.description),
            }
            columns_data.append(col_data)

        """
        Additional possible attributes to send:
        column.name = physical name
        column.choice.choices = permissible_values
        """
        return columns_data


@dataclass
class Connector:
    graph: Graph
    site_id: str

    async def get_sharepoint_lists(self):
        # Get all lists for a SharePoint site
        lists = await self.graph.app_client.sites.by_site_id(self.site_id).lists.get()
        return lists.value


    async def get_list_columns(self, list_id: str):
        # Fetch columns for a specific SharePoint list
        columns = await self.graph.app_client.sites.by_site_id(self.site_id).lists.by_list_id(list_id).columns.get()
        return columns.value
