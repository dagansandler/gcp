import httplib2
from oauth2client.contrib import gce
from apiclient.discovery import build
from apiclient.errors import HttpError
import json
import time
import sys
import os
from opereto.helpers.services import ServiceTemplate
from opereto.utils.validations import JsonSchemeValidator
from opereto.exceptions import *

class ServiceRunner(ServiceTemplate):

    def __init__(self, **kwargs):
        ServiceTemplate.__init__(self, **kwargs)

    def setup(self):
        raise_if_not_ubuntu()

    def validate_input(self):
        input_scheme = {
            "type": "object",
            "properties" : {
                 "deployment_name": {
                     "type" : "string",
                     "minLength": 1
                 },
                 "gcp_access_credentials": {
                    "type" : "object"
                 },
                 "required": ['deployment_name', 'gcp_access_credentials'],
                 "additionalProperties": True
            }
        }
        validator = JsonSchemeValidator(self.input, input_scheme)
        validator.validate()

        self.deployment_name = self.input['deployment_name']

        self._print_step_title('Connecting to GCP..')

        current_credential_file = os.path.join(self.input['opereto_workspace'], 'client_secret.json')
        with open(current_credential_file, 'w') as cf:
            cf.write(json.dumps(self.input['gcp_access_credentials'], indent=4))

        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = current_credential_file

        credentials = gce.AppAssertionCredentials(
            scope='https://www.googleapis.com/auth/cloud-platform'
        )
        self.gcp_http_handler = credentials.authorize(httplib2.Http())
        self.gcp_deploy_manager = build('deploymentmanager', 'v2')

        print 'Connected.'


    def process(self):


        try:
            self._print_step_title('Deleting the deployment (may take few minutes)...')
            request = self.gcp_deploy_manager.deployments().delete(project=self.input['gcp_project_id'], deployment=self.deployment_name)
            response = request.execute()
            status = response['status']

            while status in ['PENDING', 'RUNNING']:
                time.sleep(30)
                try:
                    request = self.gcp_deploy_manager.deployments().get(project=self.input['gcp_project_id'],deployment=self.deployment_name)
                    response = request.execute()
                    status = response['operation']['status']
                except HttpError as err:
                    if err.resp.status==404:
                        break
            print 'Deployment deleted successfully'

        except Exception, e:
            print >> sys.stderr, 'Deployment deletion failed : %s.'%str(e)
            print >> sys.stderr, 'Please retry again later or delete the deployment directly from GCP deployment manager console.'
            return self.client.FAILURE


        return self.client.SUCCESS

    def teardown(self):
        pass



if __name__ == "__main__":
    exit(ServiceRunner().run())

