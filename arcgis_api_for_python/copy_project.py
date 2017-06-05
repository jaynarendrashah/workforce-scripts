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


def filter_users(gis, project, features, feature_option):
    """
    Ensures the worker is not already added and that the work has a named user
    :param gis: (GIS) The gis to use for searching
    :param projectId: (string) The project Id
    :param workers: List<dict> The workers to add
    :return: List<dict> The list of workers to add
    """

    # Grab the item
    logger = logging.getLogger()
    features_in_fs = arcgis.features.FeatureLayer(project[feature_option]["url"], gis).query().features

    features_to_add = []
    for feature in features:
        if not user_exists(gis, feature.attributes["userId"]):
            logger.warning("User '{}' does not exist in your org and will not be added".format(feature.attributes["userId"]))
        elif feature.attributes["userId"] in [f.attributes["userId"] for f in features_in_fs]:
            logger.warning("User '{}' is already part of this project and will not be added".format(feature.attributes["userId"]))
        else:
            features_to_add.append(feature)
    return features_to_add

def write_to_destination(feature_option, features, workforce_project_data, gis):

    '''
    :param feature_option:              feature considered (workers, dispatchers or assignments)
    :param features:                    values from source
    :param workforce_project_data:      destination project data
    :param gis:                         Authenticated GIS object
    '''

    logger = logging.getLogger()
    features_fl = arcgis.features.FeatureLayer(workforce_project_data[feature_option]["url"], gis)

    # Validate/Filter each worker
    logger.info("Validating " + feature_option + "...")

    if(feature_option == "workers" or feature_option == "dispatchers"):
        features = filter_users(gis, workforce_project_data, features, feature_option)
    if(feature_option == "assignments"):
        print("This is an assignment")

    if features:
        logger.info("Adding " + feature_option + "...")
        response = features_fl.edit_features(adds=arcgis.features.FeatureSet(features))
        logger.info(response)
        if(feature_option == "workers" or feature_option == "dispatchers"):
            # Need to make sure the user is part of the workforce group
            feature_ids = [f.attributes["userId"] for f in features]
            group = arcgis.gis.Group(gis, workforce_project_data["groupId"])
            logger.info("Adding " + feature_option + " to project group...")
            response = group.add_users(feature_ids)
            logger.info(response)
        logger.info("Completed")
    else:
        logger.info("There are no new and valid " + feature_option + " to add")

def read_from_source(feature_option, workforce_project_data, gis):
    features_fl = arcgis.features.FeatureLayer(workforce_project_data[feature_option]["url"], gis)

    # Read Data from source and make a Feature Set
    features_in_source = features_fl.query().features
    features = []
    new_feature_geometry = None

    print("Extracting " + feature_option + " Data from Source")
    for feature in features_in_source:
        if feature.geometry is not None:
            new_feature_geometry = feature.geometry
        new_feature_attributes = feature.attributes
        features.append(arcgis.features.Feature(geometry=new_feature_geometry, attributes=new_feature_attributes))
        new_feature_geometry = None

    return features

def main(args):
    # initialize logging
    logger = initialize_logger(args.logFile)
    # Create the GIS
    logger.info("Authenticating...")
    # First step is to get authenticate and get a valid token
    gis = arcgis.gis.GIS(args.org_url, username=args.username, password=args.password)

    # Get the source project and data
    workforce_project = arcgis.gis.Item(gis, args.source_project_id)
    logger.info("Reading Data from destination project")
    workforce_project_data = workforce_project.get_data()

    # Extracting different features from source
    workers = read_from_source("workers", workforce_project_data, gis)
    dispatchers = read_from_source("dispatchers", workforce_project_data, gis)
    assignments = read_from_source("assignments", workforce_project_data, gis)

    #Get the destination project and data
    workforce_project = arcgis.gis.Item(gis, args.destination_project_id)
    logger.info("Reading Data from destination project")
    workforce_project_data = workforce_project.get_data()

    write_to_destination("workers", workers, workforce_project_data, gis)
    write_to_destination("dispatchers", dispatchers, workforce_project_data, gis)
    write_to_destination("assignments", assignments, workforce_project_data, gis)


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
