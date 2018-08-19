#!/usr/bin/env python

import time
import yaml
import random
import logging

from Parser import Gesucht
from pgSQL_handler import pgSQL

if __name__ == '__main__':

    with open('config.yaml') as f:
        config = yaml.load(f)

    parser = Gesucht(config)
    SQL = pgSQL(config['postgreSQL'])

    listings = parser.get_listings(n=20)
    existing_listings = SQL.get_active_listings()
    new_listings = set(listings) - set(existing_listings)

    for listing in new_listings:
        metrics = parser.parse_listing(listing)
        logging.info('{url} parsed'.format(url=listing))
        SQL.insert(metrics)
        logging.info('{url} inserted to postgreSQL'.format(url=listing))
        time.sleep(random.uniform(3, 8))

    #for listing in existing_listings[:100]:
    #    if parser.is_active(listing):
    #        SQL.archive(listing)
    #        time.sleep(random.uniform(5, 10))
