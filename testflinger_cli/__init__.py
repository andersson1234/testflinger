# Copyright (C) 2017-2022 Canonical
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
TestflingerCli module
"""


import inspect
import json
import os
import sys
import time
from argparse import ArgumentParser
from datetime import datetime
import yaml

from testflinger_cli import client, config, history


# Make it easier to run from a checkout
basedir = os.path.abspath(os.path.join(__file__, ".."))
if os.path.exists(os.path.join(basedir, "setup.py")):
    sys.path.insert(0, basedir)


def cli():
    """Generate the TestflingerCli instance and run it"""
    try:
        tfcli = TestflingerCli()
        tfcli.run()
    except KeyboardInterrupt as exc:
        raise SystemExit from exc


def _get_image(images):
    image = ""
    flex_url = ""
    if images and images[list(images.keys())[0]].startswith("url:"):
        # If this device can take URLs, offer to let the user enter one
        # instead of just using the known images
        flex_url = "or URL for a valid image starting with http(s)://... "
    while not image or image == "?":
        image = input(
            "\nEnter the name of the image you want to use "
            + flex_url
            + "('?' to list) "
        )
        if image == "?":
            if not images:
                print(
                    "WARNING: There are no images defined for this "
                    "device. You may also provide the URL to an image "
                    "that can be booted with this device though."
                )
                continue
            for image_id in sorted(images.keys()):
                print(" " + image_id)
            continue
        if image.startswith(("http://", "https://")):
            return image
        if image not in images.keys():
            print(
                "ERROR: '{}' is not in the list of known images for "
                "that queue, please select another.".format(image)
            )
            image = ""
    return image


def _get_ssh_keys():
    ssh_keys = ""
    while not ssh_keys.strip():
        ssh_keys = input(
            "\nEnter the ssh key(s) you wish to use: "
            "(ex: lp:userid, gh:userid) "
        )
        key_list = [ssh_key.strip() for ssh_key in ssh_keys.split(",")]
        for ssh_key in key_list:
            if not ssh_key.startswith("lp:") and not ssh_key.startswith("gh:"):
                ssh_keys = ""
                print("Please enter keys in the form lp:userid or gh:userid")
    return key_list


class TestflingerCli:
    """Class for handling the Testflinger CLI"""

    def __init__(self):
        self.get_args()
        self.config = config.TestflingerCliConfig(self.args.configfile)
        server = (
            self.args.server
            or self.config.get("server")
            or os.environ.get("TESTFLINGER_SERVER")
            or "https://testflinger.canonical.com"
        )
        # Allow config subcommand without worrying about server or client
        if (
            hasattr(self.args, "func")
            and self.args.func == self.configure  # pylint: disable=W0143
        ):
            return
        if not server.startswith(("http://", "https://")):
            raise SystemExit(
                'Server must start with "http://" or "https://" '
                '- currently set to: "{}"'.format(server)
            )
        self.client = client.Client(server)
        self.history = history.TestflingerCliHistory()

    def run(self):
        """Run the subcommand specified in command line arguments"""
        if hasattr(self.args, "func"):
            raise SystemExit(self.args.func())
        print(self.help)

    def get_args(self):
        """Handle command line arguments"""
        parser = ArgumentParser()
        parser.add_argument(
            "-c",
            "--configfile",
            default=None,
            help="Configuration file to use",
        )
        parser.add_argument(
            "--server", default=None, help="Testflinger server to use"
        )
        sub = parser.add_subparsers()
        arg_artifacts = sub.add_parser(
            "artifacts",
            help="Download a tarball of artifacts saved for a specified job",
        )
        arg_artifacts.set_defaults(func=self.artifacts)
        arg_artifacts.add_argument("--filename", default="artifacts.tgz")
        arg_artifacts.add_argument("job_id")
        arg_cancel = sub.add_parser(
            "cancel", help="Tell the server to cancel a specified JOB_ID"
        )
        arg_cancel.set_defaults(func=self.cancel)
        arg_cancel.add_argument("job_id")
        arg_config = sub.add_parser(
            "config", help="Get or set configuration options"
        )
        arg_config.set_defaults(func=self.configure)
        arg_config.add_argument("setting", nargs="?", help="setting=value")
        arg_jobs = sub.add_parser(
            "jobs", help="List the previously started test jobs"
        )
        arg_jobs.set_defaults(func=self.jobs)
        arg_jobs.add_argument(
            "--status",
            "-s",
            action="store_true",
            help="Include job status (may add delay)",
        )
        arg_list_queues = sub.add_parser(
            "list-queues",
            help="List the advertised queues on the Testflinger server",
        )
        arg_list_queues.set_defaults(func=self.list_queues)
        arg_poll = sub.add_parser(
            "poll", help="Poll for output from a job until it is complete"
        )
        arg_poll.set_defaults(func=self.poll)
        arg_poll.add_argument(
            "--oneshot",
            "-o",
            action="store_true",
            help="Get latest output and exit immediately",
        )
        arg_poll.add_argument("job_id")
        arg_reserve = sub.add_parser(
            "reserve", help="Install and reserve a system"
        )
        arg_reserve.set_defaults(func=self.reserve)
        arg_reserve.add_argument(
            "--queue", "-q", help="Name of the queue to use"
        )
        arg_reserve.add_argument(
            "--image", "-i", help="Name of the image to use for provisioning"
        )
        arg_reserve.add_argument(
            "--key",
            "-k",
            nargs="*",
            help=(
                "Ssh key(s) to use for reservation "
                "(ex: -k lp:userid -k gh:userid)"
            ),
        )
        arg_results = sub.add_parser(
            "results", help="Get results JSON for a completed JOB_ID"
        )
        arg_results.set_defaults(func=self.results)
        arg_results.add_argument("job_id")
        arg_show = sub.add_parser(
            "show", help="Show the requested job JSON for a specified JOB_ID"
        )
        arg_show.set_defaults(func=self.show)
        arg_show.add_argument("job_id")
        arg_status = sub.add_parser(
            "status", help="Show the status of a specified JOB_ID"
        )
        arg_status.set_defaults(func=self.status)
        arg_status.add_argument("job_id")
        arg_submit = sub.add_parser(
            "submit", help="Submit a new test job to the server"
        )
        arg_submit.set_defaults(func=self.submit)
        arg_submit.add_argument("--poll", "-p", action="store_true")
        arg_submit.add_argument("--quiet", "-q", action="store_true")
        arg_submit.add_argument("filename")

        self.args = parser.parse_args()
        self.help = parser.format_help()

    def status(self):
        """Show the status of a specified JOB_ID"""
        try:
            job_state = self.client.get_status(self.args.job_id)
            self.history.update(self.args.job_id, job_state)
        except client.HTTPError as exc:
            if exc.status == 204:
                raise SystemExit(
                    "No data found for that job id. Check the "
                    "job id to be sure it is correct"
                ) from exc
            if exc.status == 400:
                raise SystemExit(
                    "Invalid job id specified. Check the job "
                    "id to be sure it is correct"
                ) from exc
            if exc.status == 404:
                raise SystemExit(
                    "Received 404 error from server. Are you "
                    "sure this is a testflinger server?"
                ) from exc
        print(job_state)

    def cancel(self, job_id=None):
        """Tell the server to cancel a specified JOB_ID"""
        if not job_id:
            try:
                job_id = self.args.job_id
            except AttributeError as exc:
                raise SystemExit("No job id specified to cancel.") from exc
        try:
            self.client.put(f"/v1/job/{job_id}/action", {"action": "cancel"})
            self.history.update(job_id, "cancelled")
        except client.HTTPError as exc:
            if exc.status == 400:
                raise SystemExit(
                    "Invalid job ID specified or the job is already "
                    "completed/cancelled."
                ) from exc
            if exc.status == 404:
                raise SystemExit(
                    "Received 404 error from server. Are you "
                    "sure this is a testflinger server?"
                ) from exc

    def configure(self):
        """Print or set configuration values"""
        if self.args.setting:
            setting = self.args.setting.split("=")
            if len(setting) == 2:
                self.config.set(*setting)
                return
            if len(setting) == 1:
                print(
                    "{} = {}".format(setting[0], self.config.get(setting[0]))
                )
                return
        print("Current Configuration")
        print("---------------------")
        for k, v in self.config.data.items():
            print("{} = {}".format(k, v))
        print()

    def submit(self):
        """Submit a new test job to the server"""
        if self.args.filename == "-":
            data = sys.stdin.read()
        else:
            try:
                with open(
                    self.args.filename, encoding="utf-8", errors="ignore"
                ) as job_file:
                    data = job_file.read()
            except FileNotFoundError as exc:
                raise SystemExit(
                    "File not found: {}".format(self.args.filename)
                ) from exc
        job_id = self.submit_job_data(data)
        queue = yaml.safe_load(data).get("job_queue")
        self.history.new(job_id, queue)
        if self.args.quiet:
            print(job_id)
        else:
            print("Job submitted successfully!")
            print("job_id: {}".format(job_id))
        if self.args.poll:
            self.do_poll(job_id)

    def submit_job_data(self, data):
        """Submit data that was generated or read from a file as a test job"""
        try:
            job_id = self.client.submit_job(data)
        except client.HTTPError as exc:
            if exc.status == 400:
                raise SystemExit(
                    "The job you submitted contained bad data or "
                    "bad formatting, or did not specify a "
                    "job_queue."
                ) from exc
            if exc.status == 404:
                raise SystemExit(
                    "Received 404 error from server. Are you "
                    "sure this is a testflinger server?"
                ) from exc
            # This shouldn't happen, so let's get more information
            raise SystemExit(
                "Unexpected error status from testflinger "
                "server: {}".format(exc.status)
            ) from exc
        return job_id

    def show(self):
        """Show the requested job JSON for a specified JOB_ID"""
        try:
            results = self.client.show_job(self.args.job_id)
        except client.HTTPError as exc:
            if exc.status == 204:
                raise SystemExit("No data found for that job id.") from exc
            if exc.status == 400:
                raise SystemExit(
                    "Invalid job id specified. Check the job id "
                    "to be sure it is correct"
                ) from exc
            if exc.status == 404:
                raise SystemExit(
                    "Received 404 error from server. Are you "
                    "sure this is a testflinger server?"
                ) from exc
            # This shouldn't happen, so let's get more information
            raise SystemExit(
                "Unexpected error status from testflinger "
                "server: {}".format(exc.status)
            ) from exc
        print(json.dumps(results, sort_keys=True, indent=4))

    def results(self):
        """Get results JSON for a completed JOB_ID"""
        try:
            results = self.client.get_results(self.args.job_id)
        except client.HTTPError as exc:
            if exc.status == 204:
                raise SystemExit("No results found for that job id.") from exc
            if exc.status == 400:
                raise SystemExit(
                    "Invalid job id specified. Check the job id "
                    "to be sure it is correct"
                ) from exc
            if exc.status == 404:
                raise SystemExit(
                    "Received 404 error from server. Are you "
                    "sure this is a testflinger server?"
                ) from exc
            # This shouldn't happen, so let's get more information
            raise SystemExit(
                "Unexpected error status from testflinger "
                "server: {}".format(exc.status)
            ) from exc

        print(json.dumps(results, sort_keys=True, indent=4))

    def artifacts(self):
        """Download a tarball of artifacts saved for a specified job"""
        print("Downloading artifacts tarball...")
        try:
            self.client.get_artifact(self.args.job_id, self.args.filename)
        except client.HTTPError as exc:
            if exc.status == 204:
                raise SystemExit(
                    "No artifacts tarball found for that job id."
                ) from exc
            if exc.status == 400:
                raise SystemExit(
                    "Invalid job id specified. Check the job id "
                    "to be sure it is correct"
                ) from exc
            if exc.status == 404:
                raise SystemExit(
                    "Received 404 error from server. Are you "
                    "sure this is a testflinger server?"
                ) from exc
            # This shouldn't happen, so let's get more information
            raise SystemExit(
                "Unexpected error status from testflinger "
                "server: {}".format(exc.status)
            ) from exc
        print("Artifacts downloaded to {}".format(self.args.filename))

    def poll(self):
        """Poll for output from a job until it is complete"""
        if self.args.oneshot:
            # This could get an IOError for connection errors or timeouts
            # Raise it since it's not running continuously in this mode
            output = self.get_latest_output(self.args.job_id)
            if output:
                print(output, end="", flush=True)
            sys.exit(0)
        self.do_poll(self.args.job_id)

    def do_poll(self, job_id):
        """Poll for output from a running job and print it while it runs

        :param str job_id: Job ID
        """
        job_state = self.get_job_state(job_id)
        self.history.update(job_id, job_state)
        prev_queue_pos = None
        if job_state == "waiting":
            print("This job is waiting on a node to become available.")
        while job_state != "complete":
            if job_state == "cancelled":
                break
            try:
                if job_state == "waiting":
                    try:
                        queue_pos = self.client.get_job_position(job_id)
                        if int(queue_pos) != prev_queue_pos:
                            prev_queue_pos = int(queue_pos)
                            print("Jobs ahead in queue: {}".format(queue_pos))
                    except (IOError, client.HTTPError):
                        # Ignore/retry any connection errors or timeouts
                        pass
                time.sleep(10)
                output = ""
                try:
                    output = self.get_latest_output(job_id)
                except IOError:
                    # Any kind of IOError here should be a connection issue or
                    # a timeout so we should ignore it and retry on the next
                    # pass through the loop
                    continue
                if output:
                    print(output, end="", flush=True)
                job_state = self.get_job_state(job_id)
                self.history.update(job_id, job_state)
            except KeyboardInterrupt:
                choice = input(
                    "\nCancel job {} before exiting "
                    "(y)es/(N)o/(c)ontinue? ".format(job_id)
                )
                if choice:
                    choice = choice[0].lower()
                    if choice == "c":
                        continue
                    if choice == "y":
                        self.cancel(job_id)
                # Both y and n will allow the external handler deal with it
                raise

        print(job_state)

    def jobs(self):
        """List the previously started test jobs"""
        if self.args.status:
            # Getting job state may be slow, only include if requested
            status_text = "Status"
        else:
            status_text = ""
        print(
            "{:36} {:9} {}  {}".format(
                "Job ID", status_text, "Submission Time", "Queue"
            )
        )
        print("-" * 79)
        for job_id, jobdata in self.history.history.items():
            if self.args.status:
                job_state = jobdata.get("job_state")
                if job_state not in ("cancelled", "complete"):
                    job_state = self.get_job_state(job_id)
                    self.history.update(job_id, job_state)
            else:
                job_state = ""
            print(
                "{} {:9} {} {}".format(
                    job_id,
                    job_state,
                    datetime.fromtimestamp(
                        jobdata.get("submission_time")
                    ).strftime("%a %b %d %H:%M"),
                    jobdata.get("queue"),
                )
            )
        print()

    def list_queues(self):
        """List the advertised queues on the current Testflinger server"""
        try:
            queues = self.client.get_queues()
        except client.HTTPError as exc:
            if exc.status == 404:
                raise SystemExit(
                    "Received 404 error from server. Are you "
                    "sure this is a testflinger server?"
                ) from exc
        print("Advertised queues on this server:")
        for name, description in sorted(queues.items()):
            print(" {} - {}".format(name, description))

    def reserve(self):
        """Install and reserve a system"""
        try:
            queues = self.client.get_queues()
        except OSError:
            print("WARNING: unable to get a list of queues from the server!")
            queues = {}
        queue = self.args.queue or self._get_queue(queues)
        if queue not in queues.keys():
            print(
                "WARNING: '{}' is not in the list of known "
                "queues".format(queue)
            )
        try:
            images = self.client.get_images(queue)
        except OSError:
            print("WARNING: unable to get a list of images from the server!")
            images = {}
        image = self.args.image or _get_image(images)
        if (
            not image.startswith(("http://", "https://"))
            and image not in images.keys()
        ):
            raise SystemExit(
                "ERROR: '{}' is not in the list of known "
                "images for that queue, please select "
                "another.".format(image)
            )
        if image.startswith(("http://", "https://")):
            image = "url: " + image
        else:
            image = images[image]
        ssh_keys = self.args.key or _get_ssh_keys()
        for ssh_key in ssh_keys:
            if not ssh_key.startswith("lp:") and not ssh_key.startswith("gh:"):
                raise SystemExit(
                    "Please enter keys in the form lp:userid or gh:userid"
                )
        template = inspect.cleandoc(
            """job_queue: {queue}
                                    provision_data:
                                        {image}
                                    reserve_data:
                                        ssh_keys:"""
        )
        for ssh_key in ssh_keys:
            template += "\n    - {}".format(ssh_key)
        job_data = template.format(queue=queue, image=image)
        print("\nThe following yaml will be submitted:")
        print(job_data)
        answer = input("Proceed? (Y/n) ")
        if answer in ("Y", "y", ""):
            job_id = self.submit_job_data(job_data)
            print("Job submitted successfully!")
            print("job_id: {}".format(job_id))
            self.do_poll(job_id)

    def _get_queue(self, queues):
        queue = ""
        while not queue or queue == "?":
            queue = input("\nWhich queue do you want to use? ('?' to list) ")
            if not queue:
                continue
            if queue == "?":
                print("\nAdvertised queues on this server:")
                for name, description in sorted(queues.items()):
                    print(" {} - {}".format(name, description))
                queue = self._get_queue(queues)
            if queue not in queues.keys():
                print(
                    "WARNING: '{}' is not in the list of known "
                    "queues".format(queue)
                )
                answer = input("Do you still want to use it? (y/N) ")
                if answer.lower() != "y":
                    queue = ""
        return queue

    def get_latest_output(self, job_id):
        """Get the latest output from a running job

        :param str job_id: Job ID
        :return str: New output from the running job
        """
        output = ""
        try:
            output = self.client.get_output(job_id)
        except client.HTTPError as exc:
            if exc.status == 204:
                # We are still waiting for the job to start
                pass
        return output

    def get_job_state(self, job_id):
        """Return the job state for the specified job_id

        :param str job_id: Job ID
        :raises SystemExit: Exit with HTTP error code
        :return str : Job state
        """
        try:
            return self.client.get_status(job_id)
        except client.HTTPError as exc:
            if exc.status == 204:
                raise SystemExit(
                    "No data found for that job id. Check the "
                    "job id to be sure it is correct"
                ) from exc
            if exc.status == 400:
                raise SystemExit(
                    "Invalid job id specified. Check the job id "
                    "to be sure it is correct"
                ) from exc
            if exc.status == 404:
                raise SystemExit(
                    "Received 404 error from server. Are you "
                    "sure this is a testflinger server?"
                ) from exc
        return "unknown"
