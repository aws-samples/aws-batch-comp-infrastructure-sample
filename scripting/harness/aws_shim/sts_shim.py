import sys

import boto3


class STS:
    def __init__(self, sts_client):
        self.sts_client = sts_client

    def get_account_id(self) -> str:
        try:
            return self.sts_client.get_caller_identity()["Account"]
        except Exception as e:
            print(f"Error getting account ID: {e}", file=sys.stderr)
            raise e

    @staticmethod
    def get_sts_from_session(session):
        sts_client = session.client("sts")
        return STS(sts_client)

    @staticmethod
    def get_sts():
        sts = boto3.client("sts")
        return STS(sts)
