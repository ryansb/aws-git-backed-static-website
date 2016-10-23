#!/usr/bin/python2.7
#
# Lambda function for git-backed-static-website
#
# For more info, see: TBD
#
# This Lambda function is invoked by CodePipeline.
# - Download a ZIP file from the CodePipeline artifact S3 bucket
# - Unzip the contents into a temporary directory
# - Sync the contents to the S3 bucket specified in the request
#
from __future__ import print_function
from boto3.session import Session
import boto3
import botocore
import os
import zipfile
import tempfile
import shutil
import traceback

code_pipeline = boto3.client('codepipeline')

def handler(event, context):
    try:
        # Extract attributes passed in by CodePipeline
        job_id = event['CodePipeline.job']['id']
        job_data = event['CodePipeline.job']['data']
        artifact = job_data['inputArtifacts'][0]
        config = job_data['actionConfiguration']['configuration']
        credentials = job_data['artifactCredentials']
        from_bucket = artifact['location']['s3Location']['bucketName']
        from_key = artifact['location']['s3Location']['objectKey']
        from_revision = artifact['revision']
        to_bucket = config['UserParameters']

        # Temporary credentials to access CodePipeline artifact in S3
        key_id = credentials['accessKeyId']
        key_secret = credentials['secretAccessKey']
        session_token = credentials['sessionToken']
        session = Session(aws_access_key_id=key_id,
            aws_secret_access_key=key_secret,
            aws_session_token=session_token)
        s3 = session.client('s3',
            config=botocore.client.Config(signature_version='s3v4'))

        # Download from S3 the CodeCommit Git branch contents in ZIP file
        tmpdir = tempfile.mkdtemp()
        with tempfile.NamedTemporaryFile() as tmp_file:
            s3.download_file(from_bucket, from_key, tmp_file.name)
            # Unpack ZIP file
            with zipfile.ZipFile(tmp_file.name, 'r') as zip:
                zip.extractall(tmpdir)

        print('./hugo --source {} --destination {}'.format(tmpdir, tmpdir+'/public'))
        print(os.popen('./hugo --source {} --destination {}'.format(tmpdir, tmpdir+'/public')).read())
        # Sync Git branch contents to S3 bucket
        types = (
            "--exclude '*' --include '*.js' --content-type 'application/javascript' --cache-control 'max-age=7776000'",
            "--exclude '*' --include '*.css' --content-type 'text/css' --cache-control 'max-age=7776000'",
            "--exclude '*' --include '*.html' --content-type 'text/html' --cache-control 'max-age=600'",
            "--exclude '*' --include '*.xml' --content-type 'text/xml' --cache-control 'max-age=14400'",
            "--exclude '*' --include '*.png' --include '*.jpg' --include '*.jpeg' --cache-control 'max-age=7776000'",
            "--exclude '*' --include '*.otf' --include '*.eot' --include '*.svg' --include '*.ttf' --include '*.woff' --include '*.woff2' --cache-control 'max-age=7776000'",
            "--exclude '*.js' --exclude '*.css' --exclude '*.html' --exclude '*.xml' --exclude '*.png' --exclude '*.jpg' --exclude '*.jpeg' --exclude '*.svg' --exclude '*.otf' --exclude '*.eot' --exclude '*.ttf' --exclude '*.woff' --exclude '*.woff2' --cache-control 'max-age=7200'",
        )
        cmd = './aws s3 sync --acl public-read {exc_inc} {dir} s3://{bucket}/'
        for t in types:
            exec_me = cmd.format(exc_inc=t, dir=tmpdir+'/public', bucket=to_bucket)
            print(exec_me)
            print(os.popen(exec_me).read())

        # Tell CodePipeline we succeeded
        code_pipeline.put_job_success_result(jobId=job_id)

    except Exception as e:
        print(e)
        traceback.print_exc()
        # Tell CodePipeline we failed
        code_pipeline.put_job_failure_result(jobId=job_id, failureDetails={'message': e, 'type': 'JobFailed'})

    finally:
      shutil.rmtree(tmpdir)

    return "complete"
