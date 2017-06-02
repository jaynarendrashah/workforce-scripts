# -*- coding: UTF-8 -*-
"""
   Copyright 2017 Esri

   Licensed under the Apache License, Version 2.0 (the "License");

   you may not use this file except in compliance with the License.

   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software

   distributed under the License is distributed on an "AS IS" BASIS,

   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

   See the License for the specific language governing permissions and

   limitations under the License.​

   This sample copies workers from one project to another
"""

import argparse
import logging
import logging.handlers
import os
import sys
import traceback
import arcgis

def user_exists(gis, username):
    """
    Searchs the organization/portal to see if a user exists
    :param gis: (GIS) The gis to use for searching
    :param username: (string) The username to search for
    :return: True if user exists, False if not
    """
    user_manager = arcgis.gis.UserManager(gis)
    users = user_manager.search(query=username)
    return username in [x["username"] for x in users]


def filter_workers(gis, project, workers):
    """
    Ensures the worker is not already added and that the work has a named user
    :param gis: (GIS) The gis to use for searching
    :param projectId: (string) The project Id
    :param workers: List<dict> The workers to add
    :return: List<dict> The list of workers to add
    """
    # Grab the item
    logger = logging.getLogger()
    workers_in_fs = arcgis.features.FeatureLayer(project["workers"]["url"], gis).query().features

    workers_to_add = []
    for worker in workers:
        if not user_exists(gis, worker.attributes["userId"]):
            logger.warning("User '{}' does not exist in your org and will not be added".format(worker.attributes["userId"]))
        elif worker.attributes["userId"] in [w.attributes["userId"] for w in workers_in_fs]:
            logger.warning("User '{}' is already part of this project and will not be added".format(worker.attributes["userId"]))
        else:
            workers_to_add.append(worker)
    return workers_to_add

def initialize_logger(logFile):
    # Format the logger
    # The format for the logs
    formatter = logging.Formatter("[%(asctime)s] [%(filename)30s:%(lineno)4s - %(funcName)30s()]\
                     [%(threadName)5s] [%(name)10.10s] [%(levelname)8s] %(message)s")
    # Grab the root logger
    logger = logging.getLogger()
    # Set the root logger logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    logger.setLevel(logging.DEBUG)
    # Create a handler to print to the console
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    sh.setLevel(logging.INFO)
    # Create a handler to log to the specified file
    rh = logging.handlers.RotatingFileHandler(args.logFile, mode='a', maxBytes=10485760)
    rh.setFormatter(formatter)
    rh.setLevel(logging.DEBUG)
    # Add the handlers to the root logger
    logger.addHandler(sh)
    logger.addHandler(rh)
    return logger

def main(args):
    # initialize logging
    logger = initialize_logger(args.logFile)
    # Create the GIS
    logger.info("Authenticating...")
    # First step is to get authenticate and get a valid token
    gis = arcgis.gis.GIS(args.org_url, username=args.username, password=args.password)

    # Get the source project and data
    # workforce_project_source = arcgis.gis.Item(gis, args.source_project_id)
    # logger.info("Reading Data from source project")
    # workforce_project_data_source = workforce_project_source.get_data()
    # workers_fl_source = arcgis.features.FeatureLayer(workforce_project_data_source["workers"]["url"], gis)

    workforce_project = arcgis.gis.Item(gis, args.source_project_id)
    logger.info("Reading Data from destination project")
    workforce_project_data = workforce_project.get_data()
    workers_fl = arcgis.features.FeatureLayer(workforce_project_data["workers"]["url"], gis)

    # Read Data from source and make a Feature Set
    workers_in_source = workers_fl.query().features
    workers = []
    print("Extracting Data from Source")
    for worker in workers_in_source:
        new_worker_attributes = dict(
            name=worker.attributes["name"],
            status=worker.attributes["status"],
            userId=worker.attributes["userId"],
            title=worker.attributes["title"],
            contactNumber=worker.attributes["contactNumber"]
        )
        workers.append(arcgis.features.Feature(attributes=new_worker_attributes))

    print(workers)

    #Get the destination project and data
    workforce_project = arcgis.gis.Item(gis, args.destination_project_id)
    logger.info("Reading Data from destination project")
    workforce_project_data = workforce_project.get_data()
    workers_fl = arcgis.features.FeatureLayer(workforce_project_data["workers"]["url"], gis)

    # Validate/Filter each worker
    logger.info("Validating workers...")
    workers = filter_workers(gis, workforce_project_data, workers)
    if workers:
        logger.info("Adding workers...")
        response = workers_fl.edit_features(adds=arcgis.features.FeatureSet(workers))
        logger.info(response)
        # Need to make sure the user is part of the workforce group
        worker_ids = [x.attributes["userId"] for x in workers]
        group = arcgis.gis.Group(gis, workforce_project_data["groupId"])
        logger.info("Adding workers to project group...")
        response = group.add_users(worker_ids)
        logger.info(response)
        logger.info("Completed")
    else:
        logger.info("There are no new and valid workers to add")


if __name__ == "__main__":
    # Get all of the commandline arguments
    parser = argparse.ArgumentParser("Add Workers to Workforce Project")
    parser.add_argument('-u', dest='username', help="The username to authenticate with", required=True)
    parser.add_argument('-p', dest='password', help="The password to authenticate with", required=True)
    parser.add_argument('-url', dest='org_url', help="The url of the org/portal to use", required=True)
    # Parameters for workforce
    parser.add_argument('-spid', dest='source_project_id', help='The id of the source project', required=True)
    parser.add_argument('-dpid', dest='destination_project_id', help='The id of the destination project', required=True)
    parser.add_argument('-logFile', dest='logFile', help='The log file to use', required=True)
    args = parser.parse_args()
    try:
        main(args)
    except Exception as e:
        logging.getLogger().critical("Exception detected, script exiting")
        logging.getLogger().critical(e)
        logging.getLogger().critical(traceback.format_exc().replace("\n", " | "))
