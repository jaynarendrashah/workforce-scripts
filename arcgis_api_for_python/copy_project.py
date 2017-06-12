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

import json
import requests

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

def read_from_source(gis, source_workforce_project_data, feature_option):
    '''
    :param gis:                         Authenticated GIS object
    :param source_workforce_project_data:      source project data
    :param feature_option:              feature considered (workers, dispatchers or assignments)
    :return:                            List<dict> The list of features from source
    '''

    logger = logging.getLogger()
    features_fl = arcgis.features.FeatureLayer(source_workforce_project_data[feature_option]["url"], gis)
    source_features = features_fl.query().features
    return source_features

def write_to_destination(gis, destination_workforce_project_data, feature_option, source_features):

    '''
    :param gis:                         (GIS) Authenticated GIS object
    :param destination_workforce_project_data:      (string) destination project data
    :param feature_option:              (string) feature considered (workers, dispatchers or assignments)
    :param source_features:             List<dict> values from source
    :return:                            void
    '''

    logger = logging.getLogger()
    features_fl = arcgis.features.FeatureLayer(destination_workforce_project_data[feature_option]["url"], gis)

    # Validate/Filter each feature
    logger.info("Validating " + feature_option + "...")

    if feature_option == "workers" or feature_option == "dispatchers":
        source_features_to_add, source_features_to_update = filter_by_user_id(gis, destination_workforce_project_data, feature_option, source_features)

    if feature_option == "assignments" or feature_option == "tracks":
        source_features_to_add, source_features_to_update = filter_by_global_id(gis, destination_workforce_project_data, feature_option, source_features)

    if source_features_to_update:
        logger.info("Updating " + feature_option + "...")

        response = features_fl.edit_features(updates=arcgis.features.FeatureSet(source_features_to_update))
        logger.info(response)

    if source_features_to_add:
        logger.info("Adding " + feature_option + "...")

        response = features_fl.edit_features(adds=arcgis.features.FeatureSet(source_features_to_add), use_global_ids=True)
        logger.info(response)

        if feature_option == "workers" or feature_option == "dispatchers":
            # Need to make sure the user is part of the workforce group
            source_feature_ids = [f.attributes["userId"] for f in source_features_to_add]
            group = arcgis.gis.Group(gis, destination_workforce_project_data["groupId"])
            logger.info("Adding " + feature_option + " to project group...")
            response = group.add_users(source_feature_ids)
            logger.info(response)
        logger.info("Completed")
    else:
        logger.info("There are no new and valid " + feature_option + " to add")

def filter_by_global_id(gis, destination_workforce_project_data, feature_option, source_features):
    """
    Ensures the assignment is not already added
    :param gis:                     (GIS) Authenticated GIS object
    :param destination_workforce_project_data:  (string) destination project data
    :param feature_option:          (string) feature considered (workers, dispatchers or assignments)
    :param source_features:         List<dict> The users to add
    :return:                        List<dict> The list of users to add
    """

    # Grab the item
    logger = logging.getLogger()
    destination_features = arcgis.features.FeatureLayer(destination_workforce_project_data[feature_option]["url"], gis).query().features

    features_to_add = []
    features_to_update = []
    for source_feature in source_features:
        to_add_flag = True
        for f in destination_features:
            if source_feature.attributes["GlobalID"] == f.attributes["GlobalID"]:
                source_feature.attributes["OBJECTID"] = f.attributes["OBJECTID"]
                features_to_update.append(source_feature)
                to_add_flag = False
                break
        if to_add_flag:
            features_to_add.append(source_feature)
    return features_to_add, features_to_update

def filter_by_user_id(gis, destination_workforce_project_data, feature_option, source_features):
    """
    Ensures the worker is not already added and that the work has a named user
    :param gis:                     (GIS) Authenticated GIS object
    :param destination_workforce_project_data:  (string) destination project data
    :param feature_option:          (string) feature considered (workers, dispatchers or assignments)
    :param source_features:         List<dict> The users to add
    :return:                        List<dict> The list of users to add
    """

    # Grab the item
    logger = logging.getLogger()
    destination_features = arcgis.features.FeatureLayer(destination_workforce_project_data[feature_option]["url"], gis).query().features

    features_to_add = []
    features_to_update = []
    for source_feature in source_features:
        if not user_exists(gis, source_feature.attributes["userId"]):
            logger.warning("User '{}' does not exist in your org and will not be added".format(source_feature.attributes["userId"]))
        else:
            to_add_flag = True
            for f in destination_features:
                if source_feature.attributes["userId"] == f.attributes["userId"]:
                    source_feature.attributes["OBJECTID"] = f.attributes["OBJECTID"]
                    features_to_update.append(source_feature)
                    to_add_flag = False
                    break
            if to_add_flag:
                features_to_add.append(source_feature)
    return features_to_add, features_to_update

def user_exists(gis, username):
    """
    Searchs the organization/portal to see if a user exists
    :param gis:                     (GIS) The gis to use for searching
    :param username:                (string) The username to search for
    :return:                        True if user exists, False if not
    """
    user_manager = arcgis.gis.UserManager(gis)
    users = user_manager.search(query=username)
    return username in [x["username"] for x in users]

def copy_relationship(gis, source_workforce_project_data, destination_workforce_project_data, source_assignments):
    """
    Ensures the assignment is not already added
    :param gis:                     (GIS) Authenticated GIS object
    :param source_workforce_project_data:       (string) source project data
    :param destination_workforce_project_data:  (string) destination project data
    :param source_assignments:      List<dict> source assignments
    :return:                        List<dict> The list of assignments to add
    """

    source_workers = arcgis.features.FeatureLayer(source_workforce_project_data["workers"]["url"], gis).query().features
    destination_workers = arcgis.features.FeatureLayer(destination_workforce_project_data["workers"]["url"], gis).query().features

    mapping_oid = {}

    for source_worker in source_workers:
        for destination_worker in destination_workers:
            if destination_worker.attributes["userId"] == source_worker.attributes["userId"]:
                mapping_oid[source_worker.attributes["OBJECTID"]] = destination_worker.attributes["OBJECTID"]

    for source_assignment in source_assignments:
        if source_assignment.attributes["workerId"]:
            source_assignment.attributes["workerId"] = mapping_oid[source_assignment.attributes["workerId"]]


    source_dispatchers = arcgis.features.FeatureLayer(source_workforce_project_data["dispatchers"]["url"], gis).query().features
    destination_dispatchers = arcgis.features.FeatureLayer(destination_workforce_project_data["dispatchers"]["url"], gis).query().features

    mapping_oid = {}

    for source_dispatcher in source_dispatchers:
        for destination_dispatcher in destination_dispatchers:
            if destination_dispatcher.attributes["userId"] == source_dispatcher.attributes["userId"]:
                mapping_oid[source_dispatcher.attributes["OBJECTID"]] = destination_dispatcher.attributes["OBJECTID"]

    for source_assignment in source_assignments:
        if source_assignment.attributes["dispatcherId"]:
            source_assignment.attributes["dispatcherId"] = mapping_oid[source_assignment.attributes["dispatcherId"]]

    return source_assignments


def edit_web_map_obj(source_web_map_obj, destination_web_map_obj, source_workforce_project_data, destination_workforce_project_data):
    """
    Ensures the assignment is not already added
    :param source_web_map_obj:                  (WebMap) Source WebMap object
    :param destination_web_map_obj:             (WebMap) Destination WebMap object
    :param source_workforce_project_data:       (string) source project data
    :param destination_workforce_project_data:  (string) destination project data
    :return:                                    (WebMap) Updated Destination WebMap object
    """

    # copying to local copy - destination_web_map_obj
    source_web_map_dict = dict(source_web_map_obj)
    for key in source_web_map_dict:
        destination_web_map_obj[key] = source_web_map_obj[key]

    # Changing urls pointing to feature layers in destination
    feature_options = ["assignments", "workers", "dispatchers", "tracks"]
    for operationalLayer in destination_web_map_obj["operationalLayers"]:
        if operationalLayer["url"]:
            operationalLayer_url = operationalLayer["url"]
            operationalLayer_url = operationalLayer_url.replace("https:/", "http:/")

            for feature_option in feature_options:
                source_feature_url = source_workforce_project_data[feature_option]["url"]
                source_feature_url = source_feature_url.replace("https:/", "http:/")
                if operationalLayer_url == source_feature_url:
                    operationalLayer["url"] = destination_workforce_project_data[feature_option]["url"]

    return destination_web_map_obj


def main(args):

    # initialize logging
    logger = initialize_logger(args.logFile)

    # Create the GIS
    logger.info("Authenticating...")
    # First step is to get authenticate and get a valid token
    gis = arcgis.gis.GIS(args.org_url, username=args.username, password=args.password)

    # HACK: We are using private API to get the token, we uae the token to access the REST API directly
    token = gis._con._token

    # Get the source project and data
    source_workforce_project = arcgis.gis.Item(gis, args.source_project_id)
    logger.info("Connecting to source project")
    source_workforce_project_data = source_workforce_project.get_data()

    # Reading Assignment Types from source
    source_assignments_fl = arcgis.features.FeatureLayer(source_workforce_project_data["assignments"]["url"], gis)
    source_assignment_type_definition = source_assignments_fl.query().fields

    source_assignment_type_flag = False
    if type(source_assignment_type_definition)==list:
        for field in source_assignment_type_definition:
            if field["name"] == "assignmentType":
                source_assignment_type_flag = True
                source_assignment_type_definition = field


    # Extracting different features from source
    source_workers = read_from_source(gis, source_workforce_project_data, "workers")
    source_dispatchers = read_from_source(gis, source_workforce_project_data, "dispatchers")
    source_tracks = read_from_source(gis, source_workforce_project_data, "tracks")
    source_assignments = read_from_source(gis, source_workforce_project_data, "assignments")

    source_worker_web_map_item = gis.content.get(source_workforce_project_data["workerWebMapId"])
    source_worker_web_map_item_extent = source_worker_web_map_item.extent
    source_worker_web_map_obj = arcgis.mapping.WebMap(source_worker_web_map_item)

    source_dispatcher_web_map_item = gis.content.get(source_workforce_project_data["dispatcherWebMapId"])
    source_dispatcher_web_map_item_extent = source_dispatcher_web_map_item.extent
    source_dispatcher_web_map_obj = arcgis.mapping.WebMap(source_dispatcher_web_map_item)

    #Get the destination project and data
    destination_workforce_project = arcgis.gis.Item(gis, args.destination_project_id)
    logger.info("Connecting to destination project")
    destination_workforce_project_data = destination_workforce_project.get_data()

    # Writing Assignment Types to destination
    logger.info("Copying Assignment Types...")
    if source_assignment_type_flag:
        url = destination_workforce_project_data["assignments"]["url"]
        url = url.replace("rest/services", "rest/admin/services") + "/updateDefinition"

        updateDefinition = {"fields":[source_assignment_type_definition]}
        updateDefinition = json.dumps(updateDefinition)

        data = {"updateDefinition": updateDefinition, "token": token, "f": "json"}
        response = requests.post(url = url, data = data)
        logger.info(response.json())

    # Writing Features to destination
    write_to_destination(gis, destination_workforce_project_data, "workers", source_workers)
    write_to_destination(gis, destination_workforce_project_data, "dispatchers", source_dispatchers)
    write_to_destination(gis, destination_workforce_project_data, "tracks", source_tracks)

    if source_assignments:
        source_assignments = copy_relationship(gis, source_workforce_project_data, destination_workforce_project_data, source_assignments)
    else:
        logger.info("Empty source assignments")
        logger.info(source_assignments)
    write_to_destination(gis, destination_workforce_project_data, "assignments", source_assignments)

    # Copyting Assignment Integrations to destination and enabling/disabling tracking
    logger.info("Copying Assignment Integrations...")
    destination_workforce_project_data["assignmentIntegrations"] = source_workforce_project_data["assignmentIntegrations"]
    destination_workforce_project_data["tracks"]["enabled"] = source_workforce_project_data["tracks"]["enabled"]
    destination_workforce_project_data["tracks"]["updateInterval"] = source_workforce_project_data["tracks"]["updateInterval"]
    status = destination_workforce_project.update(item_properties={"text":json.dumps(destination_workforce_project_data)})
    logger.info("Copying Assignment Integrations Status: " + str(status))


    # Copying Web Maps
    logger.info("Copying Web Maps")

    destination_worker_web_map_item = gis.content.get(destination_workforce_project_data["workerWebMapId"])
    status = destination_worker_web_map_item.update(item_properties={"extent": source_worker_web_map_item_extent})
    destination_worker_web_map_obj = arcgis.mapping.WebMap(destination_worker_web_map_item)

    destination_dispatcher_web_map_item = gis.content.get(destination_workforce_project_data["dispatcherWebMapId"])
    status = destination_dispatcher_web_map_item.update(item_properties={"extent": source_dispatcher_web_map_item_extent})
    destination_dispatcher_web_map_obj = arcgis.mapping.WebMap(destination_dispatcher_web_map_item)

    destination_worker_web_map_obj = edit_web_map_obj(source_worker_web_map_obj, destination_worker_web_map_obj, source_workforce_project_data, destination_workforce_project_data)
    destination_worker_web_map_obj.update()

    destination_dispatcher_web_map_obj = edit_web_map_obj(source_dispatcher_web_map_obj, destination_dispatcher_web_map_obj, source_workforce_project_data, destination_workforce_project_data)
    destination_dispatcher_web_map_obj.update()



if __name__ == "__main__":
    # Get all of the commandline arguments
    parser = argparse.ArgumentParser("Add Workers to Workforce Project")
    parser.add_argument('-u', dest='username', help="The username to authenticate with", required=True)
    parser.add_argument('-p', dest='password', help="The password to authenticate with", required=True)
    parser.add_argument('-url', dest='org_url', help="The url of the org/portal to use", required=True)
    # Parameters for workforce
    parser.add_argument('-spid', dest='source_project_id', help='The id of the source project', required=True)
    parser.add_argument('-dpid', dest='destination_project_id', help='The id of the destination project', required=True)
    parser.add_argument('-logFile', dest='logFile', help='The log file to use', default="log.txt")
    args = parser.parse_args()
    try:
        main(args)
    except Exception as e:
        logging.getLogger().critical("Exception detected, script exiting")
        logging.getLogger().critical(e)
        # logging.getLogger().critical(traceback.format_exc().replace("\n", " | "))
        logging.getLogger().critical(traceback.format_exc())
