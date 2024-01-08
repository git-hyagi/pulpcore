import click
import logging
import os

import django

### REMOTE DEBUG
#import debugpy
#debugpy.listen(('0.0.0.0', 5678))
#debugpy.wait_for_client()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")

django.setup()

from pulpcore.tasking.worker import PulpcoreWorker  # noqa: E402: module level not at top


_logger = logging.getLogger(__name__)


@click.option("--pid", help="Write the process ID number to a file at the specified path.")
@click.option(
    "--burst/--no-burst", help="Run in burst mode; terminate when no more tasks are available."
)
@click.option(
    "--reload/--no-reload", help="Reload worker on code changes. [requires hupper to be installed.]"
)
@click.command()
def worker(pid, burst, reload):
    """A Pulp worker."""

    if reload:
        try:
            import hupper
        except ImportError:
            click.echo("Could not load hupper. This is needed to use --reload.", err=True)
            exit(1)

        hupper.start_reloader(__name__ + ".worker")

    if pid:
        with open(os.path.expanduser(pid), "w") as fp:
            fp.write(str(os.getpid()))

    _logger.info("Starting distributed type worker")
    _logger.info("It works!")

    PulpcoreWorker().run(burst=burst)
