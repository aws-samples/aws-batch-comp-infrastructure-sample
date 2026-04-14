"""List commands for displaying solver and AWS resource information."""

from typing import List

from common.misc import str_format_bytes
from harness.aws_shim import SqsQueue
from runner.commands.base import CommandContext, CommandHandler
from runner.runner_cli import LsSubcommand
from utils import Tabular


class LsCommand(CommandHandler):
    """List various solver and AWS resources."""

    def execute(self, opt: LsSubcommand = LsSubcommand.SOLVERS, **kwargs) -> int:
        """Execute the ls command based on the specified option.

        Args:
            opt: LsSubcommand specifying what to list

        Returns:
            0 on success, 1 on error
        """
        opt.print_header_message()

        if opt == LsSubcommand.SOLVERS:
            return self._ls_solvers()
        elif opt == LsSubcommand.SQS:
            return self._ls_sqs()
        elif opt == LsSubcommand.ECR:
            return self._ls_ecr()
        elif opt == LsSubcommand.ECS:
            return self._ls_ecs()
        elif opt == LsSubcommand.RESOURCES:
            return self._ls_resources()
        else:
            self.logger.error("Error: Unsupported `ls` option.")
            return 1

    def _ls_solvers(self) -> int:
        """List configured solvers.

        Returns:
            0 on success
        """
        self.logger.info(self.ctx.solvers)
        self.logger.info("")
        return 0

    def _ls_sqs(self) -> int:
        """List SQS queues and message counts.

        Returns:
            0 on success
        """
        table = Tabular(3)
        table.add_headers(["Solver", "# msgs in input", "# msgs in output"])

        sqs_client = self.ctx.get_client("sqs")
        rn = self.ctx.rn
        project = self.ctx.project
        aws_solvers = self.ctx.aws_solvers
        account = self.ctx.account

        queue_response = sqs_client.list_queues(
            QueueNamePrefix=rn.get_sqs_queue_prefix(),
            MaxResults=100,
        )

        url_prefix = f"https://sqs.{project.region}.amazonaws.com/{account}/"
        len_prefix = len(url_prefix)
        queue_urls: List[str] = [url[len_prefix:] for url in queue_response["QueueUrls"]]
        queue_urls.sort()

        def get_queue_details(queue_url: str) -> int:
            q = SqsQueue(sqs_client, queue_url)
            return q.len()

        # For each solver, find its queue, and add its information to the table
        for solver in aws_solvers:
            rn.set_solver(solver)
            q_in_url = rn.get_sqs_input_queue_name()
            q_out_url = rn.get_sqs_output_queue_name()

            try:
                # Delete the queues from the list of URLs
                index = queue_urls.index(q_in_url)
                del queue_urls[index]
                index = queue_urls.index(q_out_url)
                del queue_urls[index]

                msgs_in = get_queue_details(q_in_url)
                msgs_out = get_queue_details(q_out_url)
                table.add_row([solver, msgs_in, msgs_out])
            except ValueError:
                table.add_row([solver, "(No queues!)"])

        # Now for each leftover queue, infer its solver and list the same info
        if len(queue_urls) > 0:
            table.add_row("  (These queues are on AWS but don't match any solvers tracked by your config file)")

            num_leftover_pairs = len(queue_urls) // 2
            for i in range(num_leftover_pairs):
                q_in_url = queue_urls[2 * i]
                q_out_url = queue_urls[2 * i + 1]  # "in" comes before "out", because we sorted

                # This is hard-coded
                project_index = q_in_url.index(project.project) + (len(project.project) + 1)
                end_index = len(q_in_url) - (len(rn.INPUT_QUEUE) + 1)
                solver = q_in_url[project_index:end_index]
                msgs_in = get_queue_details(q_in_url)
                msgs_out = get_queue_details(q_out_url)
                table.add_row([solver, msgs_in, msgs_out])

        table.log(self.logger)
        self.logger.info("")
        return 0

    def _ls_ecr(self) -> int:
        """List ECR repository images.

        Returns:
            0 on success
        """
        ecr_client = self.ctx.get_client("ecr")
        rn = self.ctx.rn
        aws_solvers = self.ctx.aws_solvers

        table = Tabular(5)

        ecr_repo_name = rn.get_ecr_repo_name()
        table.add_row(f"ECR repo name: {ecr_repo_name}")
        table.add_row(f"URL: {rn.get_ecr_repo_url()}")
        table.add_headers(["Solver", "Tag", "Hash", "Size", "Pushed at"])

        ecr_response = ecr_client.describe_images(repositoryName=ecr_repo_name, filter={"tagStatus": "TAGGED"})
        tagged_images: list = ecr_response["imageDetails"]
        solvers_to_images: dict = {
            rn.get_solver_from_ecr_image_tag(image["imageTags"][0]): image for image in tagged_images
        }

        # Combine all solver names together into one list
        all_solvers = aws_solvers + list(solvers_to_images.keys())
        all_solvers = list(set(all_solvers))

        # Sort the solvers to put actively-tracked AWS solvers first
        all_solvers.sort(key=lambda x: x if x in aws_solvers else "zzz" + x)

        def get_image_details(image) -> List[str]:
            tag = image["imageTags"][0]
            hash_val = image["imageDigest"].split(":")[1][:20]
            size = str_format_bytes(image["imageSizeInBytes"])
            push_time = image["imagePushedAt"].strftime("%Y-%m-%d %H:%M:%S")
            return [tag, hash_val, size, push_time]

        added_separator = False
        for solver in all_solvers:
            if solver not in aws_solvers and not added_separator:
                table.add_row("  (These images are in the ECR repo, but are not solvers tracked by your config file)")
                added_separator = True

            if solvers_to_images.get(solver) is not None:
                image = solvers_to_images[solver]
                table.add_row([solver] + get_image_details(image))
            else:
                table.add_row([solver, "No ECR information"])

            is_distributed = False
            if is_distributed:
                # TODO: Check for "-worker"
                pass

        table.log(self.logger)
        self.logger.info("")
        return 0

    def _ls_ecs(self) -> int:
        """List ECS clusters and services.

        Returns:
            0 on success
        """
        ecs_client = self.ctx.get_client("ecs")
        rn = self.ctx.rn
        project = self.ctx.project
        aws_solvers = self.ctx.aws_solvers

        table = Tabular(5)

        table.add_row("#CI := Number of registered EC2 container instances")
        table.add_row("#D, #P, #R := Number of desired/pending/running ECS tasks")
        table.add_headers(["Solver", "#CI", "#D", "#P", "#R"])

        # Get the list of (solver) clusters for this project
        response = ecs_client.list_clusters()
        ecs_postfix = rn.get_ecs_cluster_postfix()
        cluster_arns: List[str] = response["clusterArns"]
        cluster_arns = list(filter(lambda x: project.project in x and x.endswith(ecs_postfix), cluster_arns))

        response = ecs_client.describe_clusters(clusters=cluster_arns)
        clusters: list = response["clusters"]
        solvers_to_clusters = {
            rn.get_solver_from_ecs_cluster_name(cluster["clusterName"]): cluster for cluster in clusters
        }

        all_solvers = aws_solvers + list(solvers_to_clusters.keys())
        all_solvers = list(set(all_solvers))
        all_solvers.sort(key=lambda x: x if x in aws_solvers else "zzz" + x)

        added_separator = False
        for solver in all_solvers:
            if solver not in aws_solvers and not added_separator:
                table.add_row("  (These clusters don't have a solver tracked by your config file)")
                added_separator = True

            if solvers_to_clusters.get(solver) is not None:
                cluster = solvers_to_clusters[solver]
                cluster_name = cluster["clusterName"]
                arn = cluster["clusterArn"]
                num_container_instances = cluster["registeredContainerInstancesCount"]

                # Get its service(s)
                response = ecs_client.list_services(cluster=arn)
                services = response["serviceArns"]

                # Get the stats for the service
                response = ecs_client.describe_services(
                    cluster=arn,
                    services=services,
                )
                service_stats = response["services"]

                desired_count = pending_count = running_count = 0
                for s in service_stats:
                    desired_count += s["desiredCount"]
                    pending_count += s["pendingCount"]
                    running_count += s["runningCount"]

                table.add_row([solver, num_container_instances, desired_count, pending_count, running_count])
            else:
                table.add_row([solver, "No ECS information"])

        table.log(self.logger)
        self.logger.info("")
        return 0

    def _ls_resources(self) -> int:
        """List all tagged project resources.

        Returns:
            0 on success
        """
        from common.resource_inventory_tracker import ResourceInventoryTracker

        project = self.ctx.project
        tracker = ResourceInventoryTracker(project.project, project.region)
        resources = tracker.list_all_project_resources()

        if not resources:
            self.logger.info("No tagged resources found for this project")
        else:
            table = Tabular(4)
            table.add_headers(["Resource Type", "Solver", "Resource ARN", "Created At"])

            # Group resources by solver for better organization
            grouped = tracker.group_resources_by_type()

            for resource_type, resource_list in grouped.items():
                for resource in resource_list:
                    created_at = resource.tags.get("CreatedAt", "Unknown")
                    # Truncate ARN for display
                    arn_display = resource.resource_arn
                    if len(arn_display) > 60:
                        arn_display = arn_display[:57] + "..."

                    table.add_row(
                        [
                            resource_type,
                            resource.solver,
                            arn_display,
                            created_at[:19] if created_at != "Unknown" else created_at,
                        ]
                    )

            self.logger.info(f"Found {len(resources)} tagged resources:")
            table.log(self.logger)

            # Show summary by resource type
            counts = tracker.get_resource_count()
            if counts:
                self.logger.info("\nResource count by type:")
                for resource_type, count in sorted(counts.items()):
                    self.logger.info(f"  {resource_type}: {count}")

        self.logger.info("")
        return 0
