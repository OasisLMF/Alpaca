# Alpaca

Alpaca is a command line tool for running Oasis models on throwaway EC2 instances. It
creates an instance, installs Python and OasisLMF on it, pulls down your model, runs it,
brings the results back and terminates the instance again, so nothing is left behind to pay
for.

There are four run types:

| Command | What it does |
| --- | --- |
| `alpaca model <config.json>` | Runs `oasislmf model run` against your model |
| `alpaca pytest <config.json>` | Runs your model repository's pytest suite |
| `alpaca api <config.json>` | Deploys the Oasis platform on the instance and does an API run |
| `alpaca benchmark <config.json>` | Runs the same model across several OasisLMF versions/branches and compares their timings and outputs |

Every command takes one argument: the path to an Alpaca config file. Running

```
alpaca
```

with no arguments (or with `help`, `-h` or `--help`) lists all available subcommands, and
any subcommand with `-h` (or no config) prints its usage. `alpaca version` reports the
installed version.

## Installation

```
pip install -r requirements.txt
pip install -e .
```

This puts the `alpaca` entry point on your `PATH`. For development, also install the test
dependencies:

```
pip install -r requirements-dev.txt
```

`setup.py` declares Python 3.8 or newer; CI runs the suite on Python 3.12.

## AWS login

Alpaca uses boto3 to connect to AWS. To allow your AWS account to be accessed to create
the instance, boto3 will require either you to have the environment variables
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` both set, or to have credentials in a .aws
folder, which can be obtained with the command `aws configure` using the aws cli.

If your AWS CLI uses a named profile, set the optional `AWS_PROFILE` config value; it is
applied to both the boto3 calls and the SSM tunnel.

## Connecting to instances

Alpaca connects to instances entirely over AWS Systems Manager (SSM) rather than a static
`.pem` key, so there's no `KEY_NAME` / `KEY_PATH` config or key file to manage. Each run
generates a throwaway SSH keypair in memory, authorises it on the instance for 60 seconds via
EC2 Instance Connect, and tunnels the SSH session through
`aws ssm start-session --document-name AWS-StartSSHSession`.

A few things need to be in place for that to work:

* **On your machine**: both the AWS CLI v2 and the
  [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
  must be installed and on your `PATH`. Alpaca shells out to `aws ssm start-session`, so if
  either is missing you will see connection attempts time out rather than a clear error.
* **Your AWS user or role** needs `ssm:StartSession` (on the instance and on the
  `AWS-StartSSHSession` document), `ssm:DescribeInstanceInformation` and
  `ec2-instance-connect:SendSSHPublicKey` in addition to the usual EC2 permissions
  (`ec2:RunInstances`, `ec2:CreateTags`, `ec2:DescribeInstances`,
  `ec2:TerminateInstances`, and `iam:PassRole` for `IAM_INSTANCE_PROFILE`). This is new:
  with `.pem` keys, connecting needed no SSM or Instance Connect permissions at all.
* **`IAM_INSTANCE_PROFILE`** is now a required config value, and the role behind it must let the
  SSM Agent register. The `AmazonSSMManagedInstanceCore` managed policy is enough, alongside
  whatever S3 access your run needs.
* **`AMI_ID`** must point at an image with both the SSM Agent and the `ec2-instance-connect`
  package preinstalled. Canonical's Ubuntu 20.04+ and Amazon Linux 2 images have both; a
  stripped-down custom image may not, and the failure looks like Alpaca waiting out its retries.
* **`SECURITY_GROUP_ID`** no longer needs an inbound port 22 rule, as nothing connects to the
  instance directly. Only outbound access is required (for pip, GitHub and S3).

A benchmark that uses `BENCHMARK_BUCKET` also reads and writes S3 from your own machine
rather than from the instance, so your local credentials need `s3:ListBucket`,
`s3:GetObject` and (for `PUBLISH_BASELINE`) `s3:PutObject` on that bucket.

Alpaca waits for the SSM Agent to register and then retries the SSH connection, both up to
`SSH_MAX_RETRIES` attempts three seconds apart (60 attempts, so three minutes, by default).

## Config

To use Alpaca, first create an alpaca config. This can be easily done by the command

```
alpaca create-config
```

which will list all subcommands available (config varies by type). `alpaca create-config
model`, `... pytest`, `... api` and `... benchmark` skip the prompt and go straight to that
type. Examples of Alpaca config can be found in the `example_configs` folder, and the config
creation tool will assist you in creating your own by providing help text and defaults
for all given options. The result is saved wherever you ask, defaulting to
`./myalpacaconfig.json`.

To override config that is missing from your config file, you can set the environment
variable `ALPACA_{config}`, which will replace the config if it is missing from your config
file. Please note that `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are boto3 environment
variables and not Alpaca ones and will not have the `ALPACA_` prefix.

The benchmark keys that hold several values (`REPO_LOCATIONS`, `OASISLMF_VERSIONS`,
`OASISLMF_BRANCHES`) take a JSON array in the config file. Since an environment variable and
an interactive answer can only hold text, they also accept a JSON array as a string
(`'["2.5.6", "2.5.4"]'`) or a single bare value, which is read as a one-entry list.

Every value can be given either in its natural JSON type or as text holding it, since text
is all an environment variable or a typed answer can carry. Alpaca types each key as it
loads the config:

* **Numbers** (`DISK_GB`, `MAX_LIFETIME_HOURS`, `SSH_MAX_RETRIES`, `COMPARISON_TOLERANCE`)
  accept `100` or `"100"`, and a value that isn't a number is rejected as the config loads,
  before anything is created in AWS.
* **Switches** (`DEBUG`, `PUBLISH_BASELINE`) are on for `true` or `"True"` in any case, and
  off for anything else, so `"no"` reads as off rather than as an error.

### Required config

| Key | model | pytest | api | benchmark |
| --- | --- | --- | --- | --- |
| `AMI_ID` — Amazon Machine Image to launch | ✔ | ✔ | ✔ | ✔ |
| `SECURITY_GROUP_ID` — security group for the instance | ✔ | ✔ | ✔ | ✔ |
| `SUBNET_ID` — subnet for the instance | ✔ | ✔ | ✔ | ✔ |
| `IAM_INSTANCE_PROFILE` — instance profile granting SSM and S3 access | ✔ | ✔ | ✔ | ✔ |
| `REPO_LOCATION` — GitHub URL or `s3://bucket` holding the model | ✔ | ✔ | ✔ | |
| `REPO_LOCATIONS` — JSON array of model locations to benchmark | | | | ✔ |
| `PATH_TO_OASISLMF_JSON` — path to `oasislmf.json` within the repo | ✔ | | ✔ | ✔ |
| `PATH_TO_DOCKER_COMPOSE` — path to the compose file or deploy script | | | ✔ | |

### Optional config

| Key | Default | Applies to | Description |
| --- | --- | --- | --- |
| `AWS_REGION` | `eu-west-1` | all | Region to create the instance in |
| `AWS_PROFILE` | *(none)* | all | Named AWS CLI profile for both boto3 and the SSM tunnel |
| `INSTANCE_TYPE` | `t3.medium` | all | EC2 instance type |
| `DISK_GB` | `100` | all | Root EBS volume size in GB |
| `EC2_NAME` | `Alpaca` | all | `Name` tag of the instance (overridden per target in a benchmark) |
| `MAX_LIFETIME_HOURS` | `2` | all | Written to the instance's `ALPACA_END_TIME` tag |
| `SSH_MAX_RETRIES` | `60` | all | SSM registration and SSH-over-SSM attempts, three seconds apart |
| `LOG_LEVEL` | `INFO` | all | Log level for Alpaca, botocore, paramiko and urllib3 (upper case) |
| `DEBUG` | `False` | all | `True` steps through the run one command at a time |
| `RESULT_DIRECTORY` | `./runs` | all | Where results go: a local path, or `s3://bucket` to have the instance upload them (a benchmark needs a local path) |
| `OASISLMF_VERSION` | *(latest)* | model, pytest, api | Released OasisLMF version to pip install |
| `OASISLMF_BRANCH` | *(none)* | model, pytest, api | OasisLMF branch to install from source; takes priority over `OASISLMF_VERSION` |
| `PYTEST_ARGS` | *(none)* | pytest | Extra arguments for pytest (`-vv` is always passed) |
| `OASISLMF_VERSIONS` | `[]` | benchmark | JSON array of versions to benchmark, one target each |
| `OASISLMF_BRANCHES` | `[]` | benchmark | JSON array of branches to benchmark, one target each |
| `EXECUTION_MODE` | `parallel` | benchmark | `parallel` or `sequential` |
| `COMPARISON_TOLERANCE` | `1e-6` | benchmark | Relative tolerance for numeric cells when diffing outputs |
| `BENCHMARK_BUCKET` | *(none)* | benchmark | `s3://bucket` holding versioned baseline outputs and metrics |
| `PUBLISH_BASELINE` | `False` | benchmark | `True` publishes each version target's results to `BENCHMARK_BUCKET` |

If neither `OASISLMF_VERSION` nor `OASISLMF_BRANCH` is set, the latest OasisLMF release on
PyPI is installed. `MAX_LIFETIME_HOURS` only records an end time on the instance tag; Alpaca
itself terminates the instance when the run finishes, and nothing reaps an instance on that
tag unless you run something in AWS that does.

## Running a model

When you have created your config file, to use it to perform an Oasis model run, simply
use the command

```
alpaca model <path-to-config>
```

to watch your instance be spun up and your results saved either back to your computer or
up in S3 depending on your configuration. The run's own output, including the
`COMPLETED: <step> in <seconds>s` lines OasisLMF reports per stage, is teed into
`runs/result.txt` so it comes back with the results.

A run that exits non-zero fails the command rather than reporting success. Results are
downloaded either way, so a failed run's partial output and logs are still there to look at.

## Running pytests

Simply use the command

```
alpaca pytest <path-to-config>
```

to do the same thing with any tests you have for a model. The repository is pulled to the
instance, pytest (plus hypothesis, mock and responses) is installed, and
`pytest . -vv $PYTEST_ARGS` is run with its output saved to a timestamped file under
`pytest_logs/`, which is what gets downloaded. A failing suite fails the command, so an
unattended run doesn't look green when it isn't; the logs come back either way.

## Running on the platform

For the platform run, your repo must either have a docker compose file or a deployment
bash script that will start your platform. When you have created your config, use the
command

```
alpaca api <path-to-config>
```

to create a platform in EC2 and do an API run. Alpaca installs Docker Engine, brings the
stack up (`docker compose up -d --build`, or `bash -e` for a `.sh` deploy script), polls
`http://localhost:8000/healthcheck/` until it answers or roughly five minutes pass, then runs
`oasislmf api run --server-url http://localhost:8000/` and moves
`analysis_1_output.tar.gz` into `runs/` to be downloaded.

## Benchmarking

```
alpaca benchmark <path-to-config>
```

Every combination of `REPO_LOCATIONS` and `OASISLMF_VERSIONS`/`OASISLMF_BRANCHES` is a
target, and all of them are peers — there is no designated baseline. At least one model
location and one version or branch must be configured. Each target runs as an ordinary
`alpaca model` run on its own instance, named `Alpaca {model} {version}` (e.g.
`Alpaca PiWind 2.5.4`) so concurrent instances are distinguishable in the AWS console, and
downloads into its own subfolder of `RESULT_DIRECTORY` (e.g. `./runs/PiWind-2.5.4`).

`EXECUTION_MODE` decides whether the targets run `parallel` (the default: one thread and one
instance per target) or `sequential`. Parallel runs up to eight targets at a time, the rest
waiting for a slot, so a large benchmark doesn't launch dozens of instances at once; mind
your EC2 limits and spend all the same.

Alpaca prints the plan before spending anything, then for each target reads the model's own
timings out of `result.txt`. The `oasislmf.manager.interface` step is used as the model
runtime, with the wall-clock time (which includes EC2 startup, upload and download) kept
alongside it and used as a fallback if the run reported no timings.

The fastest successful target becomes the reference every other one is compared against:

* **Timings** are reported per OasisLMF step, one column per target, quickest first, each
  cell showing how far behind the quickest it was.
* **Outputs** are diffed file by file in each run's `output` directory. Files are
  checksummed first, and only on a mismatch are CSVs parsed and compared cell by cell within
  `COMPARISON_TOLERANCE` — OasisLMF's Monte Carlo sampling means two runs rarely produce
  byte-identical loss tables. Any other file that differs, or that exists in only one run, is
  reported as different.

The combined report is printed and written to `benchmark_report.txt` next to the target
result directories. Comparison is skipped (with the reason stated in the report) if fewer
than two targets succeeded or a run's `output` directory can't be found. A target that fails
is reported as failed; the others still run and report. Because the timings and comparison
are read from local files, a benchmark needs a local `RESULT_DIRECTORY` and rejects an
`s3://` one before starting anything.

### Stored S3 baselines

Setting `BENCHMARK_BUCKET` lets a benchmark reuse results instead of paying to re-run them.
Baselines are stored per OasisLMF version as `{version}/output/*` and
`{version}/performance/result.txt`.

* Any `OASISLMF_VERSIONS` entry already stored in the bucket is downloaded and treated
  exactly like a run that just finished, rather than being run on EC2. Because baselines are
  keyed by version alone, this only applies when the benchmark has a single `REPO_LOCATIONS`
  entry; with more, every version runs live.
* `PUBLISH_BASELINE` set to `True` runs every version target live and publishes its output
  and timings as that version's new stored baseline, overwriting anything already there. It
  requires `BENCHMARK_BUCKET` and at least one `OASISLMF_VERSIONS` entry; branch targets are
  skipped, having no version to publish under.

## Results

`alpaca model` and `alpaca api` download `/home/ubuntu/runs`; `alpaca pytest` downloads
`/home/ubuntu/pytest_logs`. Either way the destination is `RESULT_DIRECTORY`, defaulting to
`./runs` next to where you ran Alpaca.

To keep the download to a sensible size, `fifo`, `static` and `work` directories are skipped
entirely, and of the `input` directory only `keys.csv` and `keys-errors.csv` are kept.
Everything else comes back.

If `RESULT_DIRECTORY` is an `s3://` location, the instance uploads the results itself with
`aws s3 cp` (creating the bucket if it doesn't exist) using the same exclusions, and nothing
is downloaded to your machine.

## Debug mode

Setting the optional config value `DEBUG` to `True`
steps through the run one command at a time. Before each command Alpaca
would normally run, you are shown it and asked what to do:

* **Enter** or **x** runs the command and moves on to the next one.
* **s** skips the command entirely.
* **t** terminates the instance and stops the run.
* **anything else** is run on the instance as a command of your own, after which you are
  asked about the same command again. Use this to look around the instance, fix something
  by hand, or try a variant of the command before letting the run continue. Your input
  reaches Alpaca but not the command, so anything that waits for input of its own (an
  editor, a password prompt, `top`) will hang with no way out but Ctrl-C.

Every command's output is streamed to your terminal in debug mode, including the ones that
are normally logged only at debug level. Note that the prompt starts at the very first
setup command, so you will step through the Python and OasisLMF install before reaching
your model run, and that a failing command does not stop the run as it otherwise would:
in debug mode it is up to you to decide whether to carry on. Debug mode needs a terminal
to read from, so it cannot be used for an unattended or CI run. It is also switched off
automatically for a `parallel` benchmark, where every target would prompt for input at once
on one terminal; set `EXECUTION_MODE` to `sequential` to step through a benchmark's targets.

## Development

```
pytest                                    # no AWS account needed (moto mocks EC2/S3)
pytest --cov --cov-report=term            # coverage, as CI reports it
flake8 --max-line-length 150              # PEP8 problems
ruff check .                              # docstring presence and Google-style formatting
autopep8 --diff --exit-code --recursive --max-line-length 150 --ignore E402 .
```

Both are enforced by GitHub Actions: `unittest.yml` runs pytest with coverage on Python
3.12, and `code-quality.yml` runs flake8, ruff and autopep8. `ruff.toml` is deliberately
docstring-only — flake8 and autopep8 cover PEP8 — and requires a docstring on every
function and method outside `tests/`.

The package is laid out as a thin CLI over a shared EC2 controller:

| Module | Responsibility |
| --- | --- |
| `alpaca/cli/` | Entry point, subcommand routing, `create-config` router, banner |
| `alpaca/inputs.py` | Every config key as a `(name, description, default)` tuple |
| `alpaca/config.py` | Interactive config creation, config loading and validation |
| `alpaca/remote_controller.py` | `RemoteController`: instance lifecycle, SSH over SSM, command execution, downloads |
| `alpaca/commands.py` | Shell commands shared by all run types (Python/OasisLMF install, S3 and GitHub transfer) |
| `alpaca/model/`, `alpaca/pytest/`, `alpaca/api/` | Per-run-type config lists, commands and entry point |
| `alpaca/benchmark/` | Target planning, threaded execution, timing, output comparison, S3 baselines, reporting |

`RemoteController` is a context manager, so the instance is always terminated on the way
out, exception or not:

```python
with RemoteController(config_file, REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL) as rc:
    rc.upload_model(rc.config["REPO_LOCATION"])
    rc.run_commands(["mkdir runs", 'echo "hello world" > runs/file.txt'])
    rc.download_results()
```

## Notes

Alpaca is currently designed to be ran on instances using Ubuntu. This can be changed in
the future, but only Ubuntu instances will currently work due to the path /home/ubuntu
being used as a default.

Model repositories are cloned without authentication, so a private repo has to come from S3
rather than GitHub.

Alpaca is licensed under the BSD 3-Clause License; see `LICENSE`.

```
              04515                                           # # #
              2 52 3     x               x                       #   #
             1473173    x x             x x                       #   #
         75   44   2     x               x                        #   #
          41       13                                            #   #
              3    13           x                             # # #
   x          3     5          x x                      #
  x x        27     17          x             x        # #
   x        72      17                       x x     #     #
            75      11                        x     #       #         x
            3        464455444451                 #           #      x x
            2         27771771132  13            #             #      x
            2         3 73 37 5 37 715         #                 #
            2         3        711 7137       #                   #
            3         353435225157 735      #         OASIS         #
            12                     71      #           LMF           #
              3            732665  71    #                             #
               71  227 27   5  32  71   #                               #
               73  317 4    4  13  17 #                                   #
                3  317 4    4 713  2 #                                     #
                2  33772    4 713  4
                2 27371     4 373 17
                2 4 272     435 2 2
```
