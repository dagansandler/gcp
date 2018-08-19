## Opereto GCP services

This package is a wrapper to several operations (as listed bellow) that are commonly used by opereto users maintaining a continuous testing ecosystem in GCP cloud environment. GCP provides a comprehensive set of API calls allowing to manage every resource and perform any operation available. In case you need additional devops operations, we recommend wrapping one of the many third-party libraries or command line toos available in the market and build your own opereto services based on those tools.
The package includes two services:

| Service                               | Description                                                                                                                              |
| --------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------:| 
| services/gcp_add_deployment           | Creates a new deployment based on deployment manager template provided including opereto agents installed on remote instances as needed  | 
| services/gcp_remove_deployment        | Removes any pre-defined deployment and all of its resources                                                                    | 


### Prerequisits/dependencies
* Services are mapped to run on a standard opereto worker agent
* opereto_core_services
        
        
### Service packages documentation
* [Learn more about automation packages and how to use them](http://help.opereto.com/support/solutions/articles/9000152583-an-overview-of-service-packages)
* [Learn more how to extend this package or build custom packages](http://help.opereto.com/support/solutions/articles/9000152584-build-and-maintain-custom-packages)

