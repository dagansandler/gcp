This service creates a deployment and all of the resources described by the deployment manager template in GCP given account/project.
[Learn more about GCP Deployment Manager](https://cloud.google.com/deployment-manager/docs/)

It gets a valid deployment template as an input. In addition, it allows to automatically installing opereto agent and tools on specified instances as defined in the template.
Agent installation is performed by adding a short startup script to the metadata field of the instance resource in the deployment template. 

To require agent installation on a given instance, you have to add a tag to any relevant instance resource in your template as follows:

*"opereto-agent-os"* tag with on of the following values: linux or windows. This directs the service code which agent installation script to use.   

In addition, you may add the following optional agent tags:

*"opereto-agent-id"* - pre-defined unique agent identifier. if not provided, opereto will automatically create a unique identifier (recommended)

*opereto-agent-name"* - a display name to show in the UI

*"opereto-agent-desc"* - a short custom description about this agent

For example: 

```yaml
vm-template.jinja:
    resources:
    - name: mytesttopology
      type: compute.v1.instance
      properties:
         zone: us-central1-a
         machineType: zones/us-central1-a/machineTypes/n1-standard-1
         disks:
         - deviceName: boot
           type: PERSISTENT
           boot: true
           autoDelete: true
           initializeParams:
             sourceImage: projects/ubuntu-os-cloud/global/images/ubuntu-1404-trusty-v20180722
         networkInterfaces:
         networkInterfaces:
         - network: $(ref.cluster-network.selfLink)
           accessConfigs:
           - name: External NAT
             type: ONE_TO_ONE_NAT
      labels:
           opereto-agent-os: linux
           opereto-agent-id: mytesttopology_Node1
``` 


#### Service success criteria
Success if deployment created successfuly. Otherwise, Failure.

#### Assumptions/Limitations
* Requires that opereto worker lib is installed (see package opereto_core_services)
* Please note that currently, if you choose to install opereto agent on a given instance, the agent installation script overrides any user data specified for that instance
* Automatically removes the created deployment upon failure

