#!/usr/bin/env python 

import kopf
from kubernetes import client, config
from datetime import datetime, timedelta

@kopf.timer('limitednamespaces',interval=5.0, initial_delay=5)
def nspurger(logger, body, spec, name, status, **kwargs):
        if status.get('nspurger') and status['nspurger'].get('marked-for-deletion',False):
            if ns_exists(name):
                logger.info(f"Namespace {name} has been already marked for deletion but still exists - will retry to delete it")
            else:
                raise kopf.TemporaryError(f"Namespace {name} has already been deleted",delay=3600)

        expiration_dt = datetime.fromtimestamp(status['managed-namespace']['expiration-ts'])
        dt_now = datetime.utcnow()
        if expiration_dt < dt_now:

            if ns_exists(name):
                logger.info(f"Namespace {name} is expired - will be deleted now")
                v1api = client.CoreV1Api()
                v1api.delete_namespace(name=name)

            if spec.get('purge'):
                cr_ns = body.metadata.get('namespace','default')
                logger.debug(f"Deleting the parent {name} LimitedNamespaced from namespace {cr_ns} object as requestes by the 'purge' parameter")
                # c = config.load_config()
                # c.debug = True
                # custom_api = client.CustomObjectsApi(api_client=client.ApiClient(configuration=c))
                custom_api = client.CustomObjectsApi()
                custom_api.delete_namespaced_custom_object(
                    group="cloudowski.com",
                    version="v1alpha1",
                    name=name,
                    namespace=cr_ns,
                    plural="limitednamespaces",
                    body=client.V1DeleteOptions(),
                )

            return {
                'marked-for-deletion': True,
                'marked-for-deletion-ts': f"{expiration_dt:%H:%M:%S %d/%m/%Y}"
            }
        else:
            logger.debug(f"Namespace {name} is not expired yet (expiration set to {expiration_dt:%H:%M:%S %d/%m/%Y})")


@kopf.on.create('limitednamespaces', id="managed-namespace")
def create_namespace(spec, name, logger, **kwargs):
    expiration = spec.get('expiration')
    expiration_ts = datetime.timestamp(datetime.utcnow()+timedelta(seconds=expiration))
    expiration_dt = datetime.fromtimestamp(expiration_ts)

    logger.info(f"Creating namespace {name} with expiration set to {expiration}s (will be deleted at {expiration_ts})")

    v1api = client.CoreV1Api()
    namespace = client.V1Namespace(
        metadata=client.V1ObjectMeta(name=name)
    )

    kopf.adopt(namespace)
    obj = v1api.create_namespace(
        body=namespace
    )

    logger.info(f"Namespace {name} is created: {obj}")
    return {
        'expiration-ts': expiration_ts,
        'expiration-dt': f"{expiration_dt:%H:%M:%S %d/%m/%Y}"
        }

@kopf.on.delete('limitednamespaces')
def delete_namespace(spec, name, logger, **kwargs):
    if not ns_exists(name):
        return
    
    logger.info(f"Deleting namespace {name} because parent object is being deleted")

    v1api = client.CoreV1Api()
    v1api.delete_namespace(name)

def ns_exists(name):
    v1api = client.CoreV1Api()
    exists = True
    try:
        v1api.read_namespace(name)
    except client.exceptions.ApiException:
        exists = False
    return exists