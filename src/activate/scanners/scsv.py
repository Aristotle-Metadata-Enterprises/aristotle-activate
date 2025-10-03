"""
Structured CSV scanner
======================

Scans a CSV File and tries to process it into Aristotle things

"""

from activate.scanners.base import Scanner, VALUE_NOT_SET
from activate.utils.config import Config

from datetime import datetime
import csv


def pwint(*vals):
    return
    import inspect, ast
    frame = inspect.currentframe().f_back
    call_line = inspect.getframeinfo(frame).code_context[0].strip()
    tree = ast.parse(call_line)
    call = tree.body[0].value
    names = []
    for arg in call.args:
        if isinstance(arg, ast.Name):
            names.append(arg.id)
        else:
            # fallback: dump raw source for expr
            names.append(ast.unparse(arg))
    print(", ".join([
        f"{n}={v!r}"
        for n, v in zip(names, vals)
    ]))


class SCSVScanner(Scanner):
    name = "scsv"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = self.config.config['connector']['options']

    @property
    def active_id_namespace(self):
        """
        Only return the safe parts of the database url for the namespace
        """
        return self.options.get('prefix', "")

    def scan_metadata(self):
        return self.scan_rows()

    def scan_rows(self):
        with open(self.options['file']) as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(csv.DictReader(f)):
                self.row_to_metadata(row)

    def row_to_metadata(self, row):
        for md_conf in self.options.get('metadata_types', []):
            md_type = md_conf['metadata_type']
            pwint(md_type, md_conf['details'])
            active_id = self.spec_to_active_id(md_type, md_conf['active_id'], row)
            pwint(active_id)
            item = self.conf_to_item(md_conf, row)

    def conf_to_item(self, conf, row):
        md_type = conf['metadata_type']
        active_id = self.spec_to_active_id(md_type, conf['active_id'], row)

        item = {}
        for field, value in conf.get('fields', {}).items():
            item[field] = self.field_to_aristotle(value, row)

        if on_create := conf.get('on_create', {}):
            item['on_create'] = {}
            for field, value in on_create.items():
                item['on_create'][field] = self.field_to_aristotle(value, row)

        self.upsert_metadata(md_type, active_id, item, order_hint=conf.get('order_hint', None))

        for field, comp_conf in conf.get('components', {}).items():
            component = {}
            for sub_field, value in comp_conf.get('fields', {}).items():
                component[sub_field] = self.field_to_aristotle(value, row)

            with_order = bool(comp_conf.get('with_order', False))

            self.append_metadata_component(md_type, active_id, field, component, with_order)
            

        return item
