#!/usr/bin/env python3
"""
One-time setup: copy a small number of test formulas into the test S3 bucket.

Creates the following structure:
    s3://<bucket>/sat/easy/   (a few .cnf files)
    s3://<bucket>/smt/easy/   (a few .smt2 files)

NOTE: This script requires access to internal AWS S3 buckets containing source
formulas. External contributors will need to provide their own test formulas
or use the --sat-source and --smt-source options to specify alternate sources.

Usage:
    python -m tests.setup_test_bucket --bucket YOUR_BUCKET --sat-source s3://... --smt-source s3://...
"""

import argparse
import os
import boto3

import common.pathing as pathing


def copy_files(s3, source_uri: str, dest_bucket: str, dest_prefix: str,
               ext: str, max_files: int) -> int:
    """Copy up to max_files from source S3 URI to dest bucket/prefix."""
    src_bucket, src_prefix = pathing.split_s3_uri(source_uri)
    if not src_prefix.endswith("/"):
        src_prefix += "/"

    paginator = s3.get_paginator("list_objects_v2")
    copied = 0
    for page in paginator.paginate(Bucket=src_bucket, Prefix=src_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(ext):
                continue
            filename = key.rsplit("/", 1)[-1]
            dest_key = f"{dest_prefix}{filename}"
            copy_source = {"Bucket": src_bucket, "Key": key}
            print(f"  {key} -> s3://{dest_bucket}/{dest_key}")
            s3.copy_object(CopySource=copy_source, Bucket=dest_bucket, Key=dest_key)
            copied += 1
            if copied >= max_files:
                return copied
    return copied


def main():
    parser = argparse.ArgumentParser(description="Set up test S3 bucket with formula files")
    parser.add_argument("--bucket", default=os.environ.get("TEST_S3_BUCKET"),
                        help="Target test bucket (or set TEST_S3_BUCKET env var)")
    parser.add_argument("--sat-source", default=os.environ.get("TEST_SAT_SOURCE"),
                        help="S3 URI containing .cnf files to copy (or set TEST_SAT_SOURCE env var)")
    parser.add_argument("--smt-source", default=os.environ.get("TEST_SMT_SOURCE"),
                        help="S3 URI containing .smt2 files to copy (or set TEST_SMT_SOURCE env var)")
    parser.add_argument("--max-files", type=int, default=3,
                        help="Max files to copy per category (default: 3)")
    args = parser.parse_args()

    if not args.bucket:
        print("Error: --bucket is required (or set TEST_S3_BUCKET env var)")
        return

    if not args.sat_source and not args.smt_source:
        print("Error: At least one of --sat-source or --smt-source is required")
        print("       (or set TEST_SAT_SOURCE / TEST_SMT_SOURCE env vars)")
        return

    s3 = boto3.client("s3", region_name="us-east-1")

    # Verify bucket is accessible (create manually if it doesn't exist)
    try:
        s3.list_objects_v2(Bucket=args.bucket, MaxKeys=1)
        print(f"Bucket {args.bucket} is accessible")
    except Exception as e:
        print(f"Error: Cannot access bucket {args.bucket}: {e}")
        print("Create the bucket manually if it doesn't exist, then re-run.")
        return

    if args.sat_source:
        print(f"\nCopying SAT files from {args.sat_source}...")
        n_sat = copy_files(s3, args.sat_source, args.bucket, "sat/easy/", ".cnf", args.max_files)
        print(f"Copied {n_sat} .cnf files\n")

    if args.smt_source:
        print(f"Copying SMT files from {args.smt_source}...")
        n_smt = copy_files(s3, args.smt_source, args.bucket, "smt/easy/", ".smt2", args.max_files)
        print(f"Copied {n_smt} .smt2 files\n")

    print("Done. Test bucket is ready.")


if __name__ == "__main__":
    main()
