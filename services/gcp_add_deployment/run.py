import json
import time
import sys
import uuid
import socket
import yaml
from opereto.helpers.services import ServiceTemplate
from opereto.utils.validations import JsonSchemeValidator, default_variable_name_scheme, default_entity_name_scheme, default_entity_description_scheme
from opereto.utils.misc import retry
from opereto.exceptions import *
import pip
import os
import httplib2
from oauth2client.contrib import gce
from apiclient.discovery import build


class ServiceRunner(ServiceTemplate):

    def __init__(self, **kwargs):
        ServiceTemplate.__init__(self, **kwargs)

    def setup(self):
        raise_if_not_ubuntu()
        self.agents = {}
        self.agent_data_map = {}
        self.deployment_info={}

    def validate_input(self):

        input_scheme = {
            "type": "object",
            "properties" : {
                 "deployment_name": {
                     "type" : "string",
                     "minLength": 1
                 },
                 "gcp_project_id": {
                    "type": "string",
                    "minLength": 1
                },
                "deployment_template": {
                    "type" : ["string", "null"]
                },
                "deployment_import_templates": {
                    "type": ["string", "null"]
                },
                "deployment_parameters": {
                    "type": ["object", "null"]
                },
                 "opereto_core_tools": {
                    "type" : "boolean"
                 },
                 "opereto_container_tools": {
                    "type" : "boolean"
                 },
                "disable_rollback": {
                    "type": "boolean"
                },
                 "gcp_access_credentials": {
                    "type": "object"
                 },
                 "required": ['gcp_project_id', 'deployment_template', 'gcp_access_credentials'],
                 "additionalProperties": True
            }
        }
        validator = JsonSchemeValidator(self.input, input_scheme)
        validator.validate()

        self.install_core_tools = self.input['install_core_tools']
        self.install_container_tools = self.input['install_container_tools']
        self.agent_valid_os = ['linux', 'windows']
        self.deployment_name = self.input['deployment_name']

        if self.install_container_tools and not self.install_core_tools:
            raise Exception, 'Opereto container tools is dependant on opereto core tools. Please check the "install_core_tools" checkbox too.'

        source_user = self.client.input['opereto_originator_username']
        self.users = [source_user]
        self.owners = [source_user]


        def linux_user_data(agent_name):
            data = """ 
        items:
        - key: startup-script
          value: |
            #! /bin/bash
            curl -O https://s3.amazonaws.com/opereto_downloads/opereto-agent-latest.tar.gz
            tar -zxvf opereto-agent-latest.tar.gz
            cd opereto-agent-latest
            sudo chmod 777 -R *
            ./install.sh -b {} -u {} -p {} -n {}""".format(self.input['opereto_host'], self.input['opereto_user'], self.input['opereto_password'], agent_name)

            return data


        def windows_user_data(agent_name):

            data = """
        items:
        - key: startup-script
          value: |
            <powershell>
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            function Unzip
            {
                param([string]$zipfile, [string]$outpath)
                [System.IO.Compression.ZipFile]::ExtractToDirectory($zipfile, $outpath)
            }
            $MyDir = "c:"
            $filename = Join-Path -Path $MyDir -ChildPath "opereto-agent-latest.zip"
            $WebClient = New-Object System.Net.WebClient
            $WebClient.DownloadFile("https://s3.amazonaws.com/opereto_downloads/opereto-agent-latest.zip", "$filename")
            Unzip "$MyDir\opereto-agent-latest.zip" "$MyDir\opereto"
            cd "$MyDir\opereto\opereto-agent-latest"
            ./opereto-install.bat %s %s "%s" %s javaw
            ./opereto-start.bat
            Remove-Item $filename
            </powershell>
            <persist>true</persist>"""%(self.input['opereto_host'], self.input['opereto_user'], self.input['opereto_password'], agent_name)

            return data


        def _add_agent_installation(json_template):

            if json_template.get('resources'):
                for resource_data in json_template['resources']:

                    if resource_data["type"]=="compute.v1.instance":

                        agent_os=None
                        agent_name=None
                        agent_display_name=None
                        agent_description=None
                        agent_id_found=False

                        if resource_data['properties'].get("labels"):
                            for key, value in resource_data['properties']["labels"].items():
                                if key=='opereto-agent-os':
                                    agent_os=value
                                elif key=='opereto-agent-id':
                                    agent_id_found=True
                                    agent_name=value
                                elif key=='opereto-agent-name':
                                    agent_display_name=value
                                elif key=='opereto-agent-desc':
                                    agent_description=value

                            json_template['resources'][json_template['resources'].index(resource_data)]['properties']["labels"]['opereto-agent-id'] = agent_name.lower()  ## match gcp label value policy
                            # del json_template['resources'][json_template['resources'].index(resource_data)]['properties']["labels"]['opereto-agent-name']
                            # del json_template['resources'][json_template['resources'].index(resource_data)]['properties']["labels"]['opereto-agent-desc']

                        if agent_os:
                            if agent_os not in self.agent_valid_os:
                                raise OperetoRuntimeError('OperetoAgentOs must be one of the following: {}'.format(str(self.agent_valid_os)))
                            if not agent_name:
                                agent_name = 'agent'+str(uuid.uuid4())[:10]
                            else:
                                try:
                                    JsonSchemeValidator(agent_name, default_variable_name_scheme).validate()
                                except Exception,e:
                                    raise OperetoRuntimeError('Invalid agent identifier: {}'.format(str(e)))
                            if agent_display_name:
                                try:
                                    JsonSchemeValidator(agent_display_name, default_entity_name_scheme).validate()
                                except Exception,e:
                                    raise OperetoRuntimeError('Invalid agent name: {}'.format(str(e)))
                            if agent_description:
                                try:
                                    JsonSchemeValidator(agent_description, default_entity_description_scheme).validate()
                                except Exception,e:
                                    raise OperetoRuntimeError('Invalid agent description: {}'.format(str(e)))

                            if agent_os=='windows':
                                agent_data = windows_user_data(agent_name)
                            else:
                                agent_data = linux_user_data(agent_name)

                            self.agent_data_map[agent_name]=agent_data


                            ## currently override user data, add fix to handle addition to existing user data
                            ##
                            ##
                            json_template['resources'][json_template['resources'].index(resource_data)]['properties']["metadata"] = agent_name+'-meta-placeholder'

                            self.agents[agent_name]={
                                'agent_display_name': agent_display_name,
                                'agent_description': agent_description
                            }


            template_in_yaml = yaml.dump(json_template)
            for agent_name, agent_data in self.agent_data_map.items():
                new_template = template_in_yaml.replace(agent_name+'-meta-placeholder', agent_data)
                template_in_yaml = new_template


            return template_in_yaml


        self.deployment_template = _add_agent_installation(yaml.load(self.input['deployment_template']))
        self.deployment_import_templates = []

        if self.input['deployment_import_templates']:
            for name, content in yaml.load(self.input['deployment_import_templates']).items():
                content = _add_agent_installation(content)
                entry = {
                    "name": name,
                    "content": """{}
                            """.format(content)
                }
                self.deployment_import_templates.append(entry)

        self.deployment_exist = False

        self._print_step_title('Connecting to GCP..')

        current_credential_file = os.path.join(self.input['opereto_workspace'], 'client_secret.json')
        with open(current_credential_file, 'w') as cf:
            cf.write(json.dumps(self.input['gcp_access_credentials'], indent=4))

        os.environ['GOOGLE_APPLICATION_CREDENTIALS']=current_credential_file

        credentials = gce.AppAssertionCredentials(
            scope='https://www.googleapis.com/auth/cloud-platform'
        )
        self.gcp_http_handler = credentials.authorize(httplib2.Http())
        self.gcp_compute_manager = build('compute', 'v1')
        self.gcp_deploy_manager = build('deploymentmanager', 'v2')

        print 'Connected.'


    def process(self):

        @retry(10, 60, 1)
        def verify_that_all_agents_connected():
            for agent_name, attr in self.agents.items():
                print 'Checking if agent %s is up and running' % agent_name
                try:
                    self.client.get_agent_properties(agent_name)
                except:
                    print 'Agent %s is not up yet. Recheck in one minute..' % agent_name
                    raise
                print 'Agent %s is up and running.' % agent_name
            pass


        try:

            self.deployment_id=None
            deployment_body = {
                "name": self.deployment_name,
                "target": {
                    "config": {
                        "content": """{}
                                  """.format(self.deployment_template)

                    },
                    "imports": self.deployment_import_templates
                }
            }
            request = self.gcp_deploy_manager.deployments().insert(project=self.input['gcp_project_id'], body=deployment_body)
            response = request.execute()
            self.deployment_exist=True


            status = response['status']
            while status in ['PENDING', 'RUNNING']:
                print 'Waiting for deployment to be ready..'
                time.sleep(30)
                request = self.gcp_deploy_manager.deployments().get(project=self.input['gcp_project_id'], deployment=self.deployment_name)
                response = request.execute()
                status = response['operation']['status']

            self.client.modify_process_property('deployment_output', response)

            request = self.gcp_deploy_manager.deployments().get(project=self.input['gcp_project_id'],
                                                                deployment=self.deployment_name)
            response = request.execute()
            print 'Deployment status: {}'.format(json.dumps(response, indent=4))

            if not response['operation']['status']=='DONE':
                raise Exception, 'Deployment failed.'

            if response['operation']['progress']==100:
                print 'Deployment is ready'
            else:
                raise Exception, 'Deployment failed.'

            ## check agents installation
            try:
                verify_that_all_agents_connected()
            except:
                raise OperetoRuntimeError('One or more agents failed to install. aborting..')

            ## modify agent properties
            result = self.gcp_compute_manager.instances().list(project=self.input['gcp_project_id'], zone='us-central1-a').execute()
            for instance in result['items']:
                if instance['name'].startswith(self.deployment_name):
                    for agent_id, attr in self.agents.items():
                        if agent_id.lower()==instance['labels']['opereto-agent-id']:
                            temp_instance = instance
                            if 'metadata' in temp_instance:
                                del temp_instance['metadata']
                            self.agents[agent_id]['gcp_info']=temp_instance
                            break

            for agent_name, attr in self.agents.items():
                try:
                    self.client.modify_agent_properties(agent_name, attr)
                except Exception,e:
                    print e

                ## modify agent permissions
                permissions = {
                    'owners': self.users,
                    'users': self.owners
                }
                description = attr.get('agent_description') or 'Created by GCP deploy manager'
                agent_display_name = attr.get('agent_display_name') or agent_name
                del self.agents[agent_name]['agent_display_name']
                del self.agents[agent_name]['agent_description']
                self.client.modify_agent(agent_name, name=agent_display_name, description=description, permissions=permissions)



            if self.install_core_tools:
                install_list=[]
                for agent_name, attr in self.agents.items():
                    title = 'Installing opereto worker libraries on agent {}'.format(agent_name)
                    install_list.append(self.client.create_process(service='install_opereto_worker_libs', agent=agent_name, title=title))

                if not self.client.is_success(install_list):
                    raise OperetoRuntimeError('Failed to install opereto worker libraries on one or more agents')

                time.sleep(10)
                if self.install_container_tools:

                    install_list_2=[]
                    for agent_name, attr in self.agents.items():
                        title = 'Installing opereto container tools on agent {}'.format(agent_name)
                        install_list_2.append(self.client.create_process(service='install_docker_on_host', agent=agent_name, title=title))

                    if not self.client.is_success(install_list_2):
                        raise OperetoRuntimeError('Failed to install opereto container tools on one or more agents')

            return self.client.SUCCESS

        except Exception, e:
            ### TBD: add to service template
            import re
            err_msg = re.sub("(.{9900})", "\\1\n", str(e), 0, re.DOTALL)
            print >> sys.stderr, 'GCP deployment failed : %s.'%err_msg

            if self.deployment_exist and not self.input.get('disable_rollback'):
                print 'Rollback the deployment..'
                request = self.gcp_deploy_manager.deployments().delete(project=self.input['gcp_project_id'], deployment=self.deployment_name, deletePolicy='DELETE')
                request.execute()
            return self.client.FAILURE


    def teardown(self):
        pass



if __name__ == "__main__":
    exit(ServiceRunner().run())

