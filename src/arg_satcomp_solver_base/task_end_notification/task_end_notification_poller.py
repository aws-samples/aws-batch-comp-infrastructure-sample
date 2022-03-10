import threading
import polling2

from arg_satcomp_solver_base.solver.run_command import CommandRunner
from arg_satcomp_solver_base.task_end_notification.task_end_notifier import TaskEndNotifier


class TaskEndNotificationPoller(threading.Thread):
    task_end_notifier: TaskEndNotifier
    command_runner: CommandRunner
    previous_notification_id: str = None

    def __init__(self, task_end_notifier: TaskEndNotifier, command_runner: CommandRunner):
        threading.Thread.__init__(self)
        self.task_end_notifier = task_end_notifier
        self.command_runner = command_runner

    def run(self):
        while True:
            self.wait_for_notification()
            self.command_runner.run(cmd=["/competition/cleanup"], output_directory="/tmp")

    @polling2.poll_decorator(check_success=lambda has_notification: has_notification, step=0.5, poll_forever=True)
    def wait_for_notification(self):
        return self._check_for_notification()

    def _check_for_notification(self):
        notification_id = self.task_end_notifier.check_for_task_end(self.previous_notification_id)
        if notification_id is not None:
            self.previous_notification_id = notification_id
            return True
        return False

    @staticmethod
    def get_task_end_notification_poller():
        task_end_notifier = TaskEndNotifier.get_task_end_notifier()
        command_runner = CommandRunner("stdout.log", "stderr.log")
        return TaskEndNotificationPoller(task_end_notifier, command_runner)
