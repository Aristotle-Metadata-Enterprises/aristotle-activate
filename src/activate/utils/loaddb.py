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
